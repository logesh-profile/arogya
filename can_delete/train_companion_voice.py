import os
import sys

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import glob
import subprocess
import time

chatbot_dir = os.path.dirname(os.path.abspath(__file__))
applio_dir = os.path.join(chatbot_dir, "Applio")
if applio_dir not in sys.path:
    sys.path.insert(0, applio_dir)

os.chdir(applio_dir)

print("=" * 60)
print("[*] STARTING NATIVE COMPANION VOICE TRAINING PIPELINE")
print("=" * 60)

# Check PyTorch & CUDA
import torch
print(f"[*] PyTorch Version : {torch.__version__}")
print(f"[*] CUDA Available  : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"[*] GPU Device Name : {torch.cuda.get_device_name(0)}")
    print(f"[*] Total VRAM      : {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
else:
    print("[!] WARNING: CUDA not detected, training will be slow or fail on CPU.")

from core import (
    run_preprocess_script,
    run_extract_script,
    run_index_script,
    run_infer_script,
    logs_path,
    pretrained_selector
)

MODEL_NAME = "my_voice"
DATASET_PATH = os.path.join(applio_dir, "assets", "datasets", MODEL_NAME)
SAMPLE_RATE = 40000
CPU_CORES = 4
GPU_ID = "0"
TOTAL_EPOCHS = 150
BATCH_SIZE = 4
SAVE_EVERY_EPOCH = 25

model_log_dir = os.path.join(logs_path, MODEL_NAME)
sliced_dir = os.path.join(model_log_dir, "sliced_audios")
f0_dir = os.path.join(model_log_dir, "f0")
extracted_dir = os.path.join(model_log_dir, "extracted")

# Phase 1: Preprocess
print("\n" + "=" * 60)
print("[1/4] Checking Audio Preprocessing...")
print("=" * 60)
if os.path.exists(sliced_dir) and len(os.listdir(sliced_dir)) > 0:
    print(f"[✓] Found {len(os.listdir(sliced_dir))} sliced audio files. Slicing already done!")
else:
    print("▶ Running preprocess...")
    preprocess_res = run_preprocess_script(
        model_name=MODEL_NAME,
        dataset_path=DATASET_PATH,
        sample_rate=SAMPLE_RATE,
        cpu_cores=CPU_CORES,
        cut_preprocess="Automatic",
        process_effects=False,
        chunk_len=3.0,
        overlap_len=0.3,
        normalization_mode="none",
    )
    print(f"[+] Preprocess Result: {preprocess_res}")

# Phase 2: Feature Extraction
print("\n" + "=" * 60)
print("[2/4] Checking Feature Extraction (RMVPE Pitch + ContentVec Embeddings)...")
print("=" * 60)
f0_count = len(os.listdir(f0_dir)) if os.path.exists(f0_dir) else 0
emb_count = len(os.listdir(extracted_dir)) if os.path.exists(extracted_dir) else 0
if f0_count > 0 and emb_count > 0:
    print(f"[✓] Found {f0_count} pitch features and {emb_count} embedding features on GPU. Extraction already done!")
else:
    print("▶ Running feature extraction on GPU...")
    extract_res = run_extract_script(
        model_name=MODEL_NAME,
        f0_method="rmvpe",
        cpu_cores=CPU_CORES,
        gpu=GPU_ID,
        sample_rate=SAMPLE_RATE,
        embedder_model="contentvec",
        embedder_model_custom=None,
        include_mutes=2,
    )
    print(f"[+] Extract Result: {extract_res}")

# Phase 3: Live Training on GPU with Real-Time Output
print("\n" + "=" * 60)
print(f"[3/4] Launching GPU Training ({TOTAL_EPOCHS} epochs, batch size {BATCH_SIZE})...")
print("=" * 60)

pg, pd = pretrained_selector("HiFi-GAN", SAMPLE_RATE)
print(f"[*] Pretrained Generator     : {pg}")
print(f"[*] Pretrained Discriminator : {pd}")

train_script_path = os.path.join(applio_dir, "rvc", "train", "train.py")
cmd = [
    sys.executable,
    "-u",
    train_script_path,
    MODEL_NAME,
    str(SAVE_EVERY_EPOCH),
    str(TOTAL_EPOCHS),
    str(pg),
    str(pd),
    str(GPU_ID),
    str(BATCH_SIZE),
    str(SAMPLE_RATE),
    "False",  # save_only_latest
    "True",   # save_every_weights
    "False",  # cache_data_in_gpu
    "False",  # cleanup
    "HiFi-GAN",
    "False",  # checkpointing
]

print(f"[*] Starting train worker process on GPU {GPU_ID}...")
start_time = time.time()
process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    cwd=applio_dir,
    encoding="utf-8",
    errors="replace"
)

for line in process.stdout:
    line_clean = line.strip()
    if line_clean:
        print(f"  {line_clean}", flush=True)

process.wait()
if process.returncode != 0:
    print(f"[!] Training failed with exit code {process.returncode}")
    sys.exit(process.returncode)

elapsed = time.time() - start_time
print(f"\n[✓] Training completed successfully in {elapsed:.1f}s ({elapsed/60:.2f} mins)!")

# Phase 4: Build / Verify Index
print("\n" + "=" * 60)
print("[4/4] Verifying FAISS Acoustic Index...")
print("=" * 60)
index_file = os.path.join(model_log_dir, f"{MODEL_NAME}.index")
if not os.path.exists(index_file):
    print("▶ Building FAISS index...")
    run_index_script(MODEL_NAME, "Auto")

# Locate best weights
pth_files = sorted(glob.glob(os.path.join(model_log_dir, f"{MODEL_NAME}_*.pth")))
if not pth_files:
    pth_files = sorted(glob.glob(os.path.join(applio_dir, "assets", "weights", f"{MODEL_NAME}*.pth")))

index_files = sorted(glob.glob(os.path.join(model_log_dir, "*.index")))
if not index_files:
    index_files = sorted(glob.glob(os.path.join(applio_dir, "assets", "weights", f"{MODEL_NAME}*.index")))

print(f"\n[*] Trained Models found: {pth_files}")
print(f"[*] FAISS Indexes found : {index_files}")

if pth_files:
    latest_pth = pth_files[-1]
    latest_index = index_files[-1] if index_files else ""
    print(f"\n[*] Selected Model : {latest_pth}")
    print(f"[*] Selected Index : {latest_index}")

    input_tamil_wav = os.path.join(chatbot_dir, "gemini_audio", "companion_tamil.wav")
    output_dir = os.path.join(chatbot_dir, "final_output")
    os.makedirs(output_dir, exist_ok=True)
    output_cloned_wav = os.path.join(output_dir, "companion_native_cloned.wav")

    if os.path.exists(input_tamil_wav):
        print("\n" + "=" * 60)
        print("🔄 Transforming Gemini Native Speech through Cloned Voice Model...")
        print("=" * 60)
        infer_msg, final_wav = run_infer_script(
            pitch=0,
            index_rate=0.75,
            volume_envelope=1.0,
            protect=0.33,
            f0_method="rmvpe",
            input_path=input_tamil_wav,
            output_path=output_cloned_wav,
            pth_path=latest_pth,
            index_path=latest_index,
            split_audio=False,
            f0_autotune=False,
            f0_autotune_strength=1.0,
            proposed_pitch=False,
            proposed_pitch_threshold=155.0,
            export_format="WAV",
            embedder_model="contentvec",
        )
        print(f"[✓] {infer_msg}")
        print(f"\n✨ FINAL CLONED NATIVE AUDIO CREATED: {final_wav}")

print("\n🎉 ENTIRE PIPELINE SUCCEEDED! YOUR MODEL IS TRAINED AND VOICE CONVERTED!")
