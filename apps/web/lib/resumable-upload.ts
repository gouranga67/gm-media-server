import { defaultOptions, Upload } from "tus-js-client";

import type { Asset } from "@/lib/media-api";

type UploadCallbacks = {
  readonly onProgress: (
    uploadedBytes: number,
    totalBytes: number,
    bytesPerSecond?: number,
    etaSeconds?: number,
  ) => void;
  readonly onRetry: (attempt: number, error: Error) => void;
  readonly onError: (error: Error) => void;
  readonly onSuccess: () => void;
};

function uploadChunkSize(file: File): number {
  const connection = (navigator as Navigator & {
    connection?: { readonly effectiveType?: string; readonly saveData?: boolean };
  }).connection;
  if (connection?.saveData || ["slow-2g", "2g", "3g"].includes(connection?.effectiveType ?? "")) {
    return 2 * 1024 * 1024;
  }
  if (file.size <= 512 * 1024 * 1024) return 5 * 1024 * 1024;
  if (file.size <= 4 * 1024 * 1024 * 1024) return 10 * 1024 * 1024;
  return 20 * 1024 * 1024;
}

export async function startResumableUpload(
  file: File,
  asset: Asset,
  callbacks: UploadCallbacks,
): Promise<Upload> {
  if (asset.mime_type === null) {
    throw new Error(`${file.name} is missing its registered media type`);
  }

  let lastSampleAt = performance.now();
  let lastSampleBytes = 0;
  let smoothedRate = 0;
  const upload = new Upload(file, {
    // Next.js canonicalizes trailing slashes with a 308. Use the canonical
    // collection path so upload-creation POST requests reach tusd directly.
    endpoint: "/files",
    fingerprint: async () =>
      ["gm-media", asset.id, file.name, file.size, file.lastModified].join(":"),
    chunkSize: uploadChunkSize(file),
    retryDelays: [0, 1_000, 3_000, 5_000, 10_000, 20_000],
    removeFingerprintOnSuccess: true,
    metadata: {
      assetId: asset.id,
      projectId: asset.project_id,
      filename: file.name,
      filetype: asset.mime_type,
    },
    onProgress(uploadedBytes, totalBytes) {
      const now = performance.now();
      if (lastSampleBytes === 0 && uploadedBytes > 0 && now - lastSampleAt < 500) {
        lastSampleBytes = uploadedBytes;
        lastSampleAt = now;
        callbacks.onProgress(uploadedBytes, totalBytes);
        return;
      }
      const elapsedSeconds = (now - lastSampleAt) / 1000;
      if (uploadedBytes < lastSampleBytes) {
        lastSampleBytes = uploadedBytes;
        lastSampleAt = now;
      }
      if (elapsedSeconds >= 0.5 && uploadedBytes >= lastSampleBytes) {
        const sampleRate = (uploadedBytes - lastSampleBytes) / elapsedSeconds;
        if (sampleRate > 0) smoothedRate = smoothedRate > 0 ? smoothedRate * 0.7 + sampleRate * 0.3 : sampleRate;
        lastSampleBytes = uploadedBytes;
        lastSampleAt = now;
      }
      const eta = smoothedRate > 0 ? Math.max(0, (totalBytes - uploadedBytes) / smoothedRate) : undefined;
      callbacks.onProgress(uploadedBytes, totalBytes, smoothedRate || undefined, eta);
    },
    onShouldRetry(error, retryAttempt, options) {
      callbacks.onRetry(retryAttempt + 1, error);
      return defaultOptions.onShouldRetry?.(error, retryAttempt, options) ?? false;
    },
    onError: callbacks.onError,
    onSuccess: callbacks.onSuccess,
  });

  const previousUploads = await upload.findPreviousUploads();
  if (previousUploads.length > 0) {
    upload.resumeFromPreviousUpload(previousUploads[0]);
  }
  upload.start();
  return upload;
}
