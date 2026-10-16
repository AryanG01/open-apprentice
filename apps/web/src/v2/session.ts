// Session-state merging for polling (spec 8): responses carry manifest_revision and stale ones are ignored.
export type Revisioned = { session_id: string; manifest_revision: number };

export const accept = <T extends Revisioned>(prev: T | null, next: T): T =>
  prev !== null && prev.session_id === next.session_id && prev.manifest_revision > next.manifest_revision ? prev : next;
