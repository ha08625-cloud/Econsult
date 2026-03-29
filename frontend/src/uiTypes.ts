// UI-only types. These are never serialised or sent to the server.
// Wire-format types (server contracts) live in types.ts.

/**
 * Represents a photo the patient has attached to their submission.
 * `previewUrl` is an object URL created with URL.createObjectURL — it must be
 * revoked (URL.revokeObjectURL) when the photo is removed or the session ends.
 */
export interface PhotoAttachment {
  file: File;
  previewUrl: string;
}
