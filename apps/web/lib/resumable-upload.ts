import { Upload } from "tus-js-client";

import type { Asset } from "@/lib/media-api";

type UploadCallbacks = {
  readonly onProgress: (uploadedBytes: number, totalBytes: number) => void;
  readonly onError: (error: Error) => void;
  readonly onSuccess: () => void;
};

export async function startResumableUpload(
  file: File,
  asset: Asset,
  callbacks: UploadCallbacks,
): Promise<Upload> {
  if (asset.mime_type === null) {
    throw new Error(`${file.name} is missing its registered media type`);
  }

  const upload = new Upload(file, {
    // Next.js canonicalizes trailing slashes with a 308. Use the canonical
    // collection path so upload-creation POST requests reach tusd directly.
    endpoint: "/files",
    fingerprint: async () =>
      ["gm-media", asset.id, file.name, file.size, file.lastModified].join(":"),
    chunkSize: 20 * 1024 * 1024,
    retryDelays: [0, 1_000, 3_000, 5_000, 10_000, 20_000],
    removeFingerprintOnSuccess: true,
    metadata: {
      assetId: asset.id,
      projectId: asset.project_id,
      filename: file.name,
      filetype: asset.mime_type,
    },
    onProgress: callbacks.onProgress,
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
