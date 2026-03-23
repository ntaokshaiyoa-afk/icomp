import sys
import json
import shutil
import subprocess
import os
import uuid
from pathlib import Path
from evaluate import evaluate_quality

BASE_DIR = Path(__file__).resolve().parent.parent
BIN = BASE_DIR / "bin"

TOOLS = {
    "jpegoptim": BIN / "jpegoptim.exe",
    "cwebp": BIN / "cwebp.exe",
    "avifenc": BIN / "avifenc.exe",
    "cjxl": BIN / "cjxl.exe",
    "ffmpeg": BIN / "ffmpeg.exe",
}

SSIM_THRESHOLD = 0.995
PSNR_THRESHOLD = 38


def run(cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except:
        return False


def decode_to_png(src, dst):
    return run([
        str(TOOLS["ffmpeg"]),
        "-y",
        "-i", str(src),
        str(dst)
    ])


def evaluate_candidate(src, out_path):
    try:
        eval_path = out_path

        if out_path.suffix.lower() in [".avif", ".jxl", ".webp"]:
            png = out_path.with_suffix(".png")
            if not decode_to_png(out_path, png):
                return None
            eval_path = png

        result = evaluate_quality(src, eval_path)

        return {
            "ssim": result["ssim"],
            "psnr": result["psnr"],
            "size": os.path.getsize(out_path)
        }

    except:
        return None


# 🎯 品質探索（コア）
def optimize_quality(src, work_dir, fmt):
    best = None

    q_min = 50
    q_max = 100

    for _ in range(6):
        q = (q_min + q_max) // 2

        if fmt == "webp":
            out = work_dir / f"{fmt}_{q}.webp"
            ok = run([str(TOOLS["cwebp"]), "-q", str(q), str(src), "-o", str(out)])

        elif fmt == "avif":
            out = work_dir / f"{fmt}_{q}.avif"
            ok = run([str(TOOLS["avifenc"]), "-q", str(q), str(src), str(out)])

        elif fmt == "jxl":
            out = work_dir / f"{fmt}_{q}.jxl"
            distance = max(0.1, (100 - q) / 20)
            ok = run([str(TOOLS["cjxl"]), str(src), str(out), "-d", str(distance)])

        else:
            return None

        if not ok or not out.exists():
            continue

        info = evaluate_candidate(src, out)
        if not info:
            continue

        if info["ssim"] >= SSIM_THRESHOLD and info["psnr"] >= PSNR_THRESHOLD:
            if best is None or info["size"] < best["size"]:
                best = {
                    "path": out,
                    "size": info["size"],
                    "ssim": info["ssim"],
                    "psnr": info["psnr"],
                    "q": q
                }
            q_max = q
        else:
            q_min = q

    return best


def process_file(src: Path, dst_root: Path, base: Path):
    rel = src.relative_to(base)
    dst_dir = dst_root / rel.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    work_dir = dst_dir / f"__tmp_{uuid.uuid4().hex}"
    work_dir.mkdir()

    candidates = []

    # 元
    original_size = os.path.getsize(src)
    candidates.append({
        "name": "original",
        "path": str(src),
        "size": original_size,
        "ssim": 1.0,
        "psnr": 100
    })

    # jpegoptim
    if TOOLS["jpegoptim"].exists():
        out = work_dir / "opt.jpg"
        try:
            subprocess.run([
                str(TOOLS["jpegoptim"]),
                "--strip-all",
                "--all-progressive",
                "--stdout",
                str(src)
            ], stdout=open(out, "wb"), check=True)

            info = evaluate_candidate(src, out)
            if info:
                candidates.append({
                    "name": "jpegoptim",
                    "path": str(out),
                    **info
                })
        except:
            pass

    # 🔥 品質探索
    for fmt in ["webp", "avif", "jxl"]:
        best = optimize_quality(src, work_dir, fmt)
        if best:
            candidates.append({
                "name": fmt,
                "path": str(best["path"]),
                "size": best["size"],
                "ssim": best["ssim"],
                "psnr": best["psnr"],
                "quality": best["q"]
            })

    # ログ
    print(f"\n[FILE] {src}")
    for c in candidates:
        print(f"  {c['name']:10} size={c['size']:10} ssim={c['ssim']:.5f} psnr={c['psnr']:.2f}")

    # 最小選択
    valid = [
        c for c in candidates
        if c["ssim"] >= SSIM_THRESHOLD and c["psnr"] >= PSNR_THRESHOLD
    ]

    if not valid:
        best = candidates[0]
    else:
        best = min(valid, key=lambda x: x["size"])

    ext_map = {
        "original": src.suffix,
        "jpegoptim": ".jpg",
        "webp": ".webp",
        "avif": ".avif",
        "jxl": ".jxl",
    }

    final_path = dst_dir / (src.stem + ext_map[best["name"]])

    if best["name"] == "original":
        shutil.copy2(src, final_path)
    else:
        shutil.move(best["path"], final_path)

    shutil.rmtree(work_dir)

    return {
        "file": str(src),
        "output": str(final_path),
        "method": best["name"],
        "size": best["size"],
        "ssim": best["ssim"],
        "psnr": best["psnr"]
    }


def main():
    if len(sys.argv) < 3:
        print("usage: python pipeline_v4.py input_dir output_dir")
        return

    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    files = [
        p for p in input_dir.rglob("*")
        if p.suffix.lower() in [".jpg", ".jpeg"]
    ]

    results = []

    for p in files:
        try:
            results.append(process_file(p, output_dir, input_dir))
        except Exception as e:
            results.append({"file": str(p), "error": str(e)})

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
