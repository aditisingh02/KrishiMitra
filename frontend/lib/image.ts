/**
 * Client-side image downscaling for crop photos.
 *
 * Why: a modern phone camera produces a 12MP / 3-8MB JPEG. Uploading that raw
 * over rural mobile data is, by a wide margin, the slowest part of a diagnosis -
 * a 4MB photo on a ~500kbps uplink is ~65s of upload before any AI even starts.
 * It also inflates the vision model's image-token prefill.
 *
 * Downscaling to 1280px long edge cuts it to ~200-300KB with no meaningful loss
 * of diagnostic detail: vision models tile at roughly 1024-1568px and downscale
 * internally anyway, so the extra pixels are discarded server-side regardless.
 *
 * Do NOT lower MAX_EDGE below 1024 - early-stage speckling and lesion margins
 * genuinely disappear below that, and correctly reading those is the entire
 * point of the product.
 */

/** Long-edge target. Above the model's ~1024 tiling threshold, with headroom. */
const MAX_EDGE = 1280;
const QUALITY = 0.85;

export type DownscaleResult = {
  file: File;
  /** Object URL for previewing - caller must revokeObjectURL when done. */
  previewUrl: string;
  originalBytes: number;
  bytes: number;
  /** False when we deliberately kept the original (already small, or decode failed). */
  resized: boolean;
};

function isDownscalable(file: File): boolean {
  // HEIC/HEIF often can't be decoded by canvas; GIF/SVG make no sense to re-encode.
  return /^image\/(jpeg|png|webp)$/i.test(file.type);
}

/**
 * Decode with EXIF orientation applied.
 *
 * Phone photos are usually stored sideways with an EXIF orientation flag. Drawing
 * to a canvas drops that flag, so a naive re-encode silently rotates the crop
 * photo - which we'd then hand to the vision model. `imageOrientation: "from-image"`
 * bakes the rotation into the pixels instead.
 */
async function decode(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === "function") {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  }
  // Safari fallback: <img> applies EXIF orientation itself when rendering.
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("decode failed"));
      img.src = url;
    });
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Downscale `file` to at most MAX_EDGE on its long side.
 *
 * Never throws: on any failure (unsupported codec, decode error, canvas blocked)
 * it returns the original file. A slower upload beats a broken diagnosis.
 */
export async function downscaleImage(file: File): Promise<DownscaleResult> {
  const original = () => ({
    file,
    previewUrl: URL.createObjectURL(file),
    originalBytes: file.size,
    bytes: file.size,
    resized: false,
  });

  if (!isDownscalable(file)) return original();

  try {
    const img = await decode(file);
    const w = "width" in img ? img.width : 0;
    const h = "height" in img ? img.height : 0;
    if (!w || !h) return original();

    // Already small enough - don't re-encode, that's pure generation loss.
    if (Math.max(w, h) <= MAX_EDGE) {
      if ("close" in img) img.close();
      return original();
    }

    const scale = MAX_EDGE / Math.max(w, h);
    const tw = Math.round(w * scale);
    const th = Math.round(h * scale);

    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d");
    if (!ctx) return original();
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img as CanvasImageSource, 0, 0, tw, th);
    if ("close" in img) img.close();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", QUALITY),
    );
    if (!blob) return original();

    // If re-encoding somehow grew the file, keep the original.
    if (blob.size >= file.size) return original();

    const name = file.name.replace(/\.[^.]+$/, "") || "photo";
    const resizedFile = new File([blob], `${name}.jpg`, { type: "image/jpeg" });
    return {
      file: resizedFile,
      previewUrl: URL.createObjectURL(blob),
      originalBytes: file.size,
      bytes: blob.size,
      resized: true,
    };
  } catch {
    return original();
  }
}
