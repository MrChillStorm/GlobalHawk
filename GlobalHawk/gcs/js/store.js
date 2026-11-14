/**
 * A small keeper of things worth not downloading twice (airports, airspace): IndexedDB where the page has it, memory
 * where it does not (a file page in some browsers, a private window, node). It never throws: a store that fails is
 * a store that forgets, and the page goes on without it.
 */
(function (root) {
  'use strict';

  class Store {
    constructor(name, idb) {
      this.name = name || 'gcs-data';
      this.mem = new Map();
      this.db = null;
      const factory = idb === undefined ? (typeof indexedDB !== 'undefined' ? indexedDB : null) : idb;
      this.ready = new Promise((resolve) => {
        if (!factory) return resolve(null);
        try {
          const req = factory.open(this.name, 1);
          req.onupgradeneeded = () => req.result.createObjectStore('kv');
          req.onsuccess = () => {
            this.db = req.result;
            resolve(this.db);
          };
          req.onerror = () => resolve(null);
          req.onblocked = () => resolve(null);
        } catch (e) {
          resolve(null);
        }
      });
    }

    async get(key) {
      await this.ready;
      if (this.mem.has(key)) return this.mem.get(key);
      if (!this.db) return undefined;
      return new Promise((resolve) => {
        try {
          const r = this.db.transaction('kv').objectStore('kv').get(key);
          r.onsuccess = () => resolve(r.result);
          r.onerror = () => resolve(undefined);
        } catch (e) {
          resolve(undefined);
        }
      });
    }

    async set(key, value) {
      await this.ready;
      this.mem.set(key, value);
      if (!this.db) return false;
      return new Promise((resolve) => {
        try {
          const tx = this.db.transaction('kv', 'readwrite');
          tx.objectStore('kv').put(value, key);
          tx.oncomplete = () => resolve(true);
          tx.onerror = () => resolve(false);
          tx.onabort = () => resolve(false);
        } catch (e) {
          resolve(false);
        }
      });
    }

    async del(key) {
      await this.ready;
      this.mem.delete(key);
      if (!this.db) return;
      await new Promise((resolve) => {
        try {
          const tx = this.db.transaction('kv', 'readwrite');
          tx.objectStore('kv').delete(key);
          tx.oncomplete = tx.onerror = tx.onabort = () => resolve();
        } catch (e) {
          resolve();
        }
      });
    }
  }

  const api = { Store };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else (root.GCS = root.GCS || {}).store = api;
})(typeof window !== 'undefined' ? window : globalThis);
