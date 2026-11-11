/**
 * Caches the bulk dataset (questions/sessions/members/tags — ~28MB combined)
 * in IndexedDB so repeat visits skip re-downloading it on every full page
 * load. Keyed by data_version.json's hash, which the pipeline only changes
 * when questions/sessions/members/tags actually change content.
 */

const DB_NAME = 'kvizzing-cache';
const STORE_NAME = 'data';
const DB_VERSION = 1;
const ENTRY_KEY = 'bulk-data';

export type BulkData = {
  version: string;
  questions: unknown;
  sessions: unknown;
  members: unknown;
  tags: unknown;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE_NAME);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet<T>(key: string): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).get(key);
    req.onsuccess = () => resolve(req.result as T | undefined);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(key: string, value: unknown): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Returns the cached bulk dataset if its stored version matches
 * `currentVersion`, otherwise undefined — caller should fetch fresh in
 * that case. Never throws: IndexedDB can be unavailable (private browsing,
 * blocked storage) and that just means every load re-fetches over network.
 */
export async function getCachedBulkData(currentVersion: string): Promise<BulkData | undefined> {
  try {
    const cached = await idbGet<BulkData>(ENTRY_KEY);
    if (cached && cached.version === currentVersion) return cached;
  } catch {
    // Fall through to network fetch.
  }
  return undefined;
}

export async function setCachedBulkData(data: BulkData): Promise<void> {
  try {
    await idbSet(ENTRY_KEY, data);
  } catch {
    // Best-effort — losing the cache just means the next load re-fetches.
  }
}
