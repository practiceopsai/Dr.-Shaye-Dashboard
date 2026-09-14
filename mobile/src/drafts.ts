import * as SecureStore from 'expo-secure-store';
const key = (owner: string, kind: string) => `eli.draft.${Array.from(`${owner}:${kind}`).map(c => c.charCodeAt(0).toString(16)).join('')}`;
let writes = Promise.resolve();
export const drafts = {
  async load(owner: string, kind: string) {
    await writes.catch(() => undefined);
    return await SecureStore.getItemAsync(key(owner, kind)) || '';
  },
  save(owner: string, kind: string, value: string) {
    const operation = writes.catch(() => undefined).then(() => value
      ? SecureStore.setItemAsync(key(owner, kind), value, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY })
      : SecureStore.deleteItemAsync(key(owner, kind)));
    writes = operation;
    return operation;
  },
  flush: () => writes,
};
