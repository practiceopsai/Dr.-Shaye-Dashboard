// Layout review never persists private information to browser storage.
export const drafts = { load: async (_owner: string, _kind: string) => '', save: async (_owner: string, _kind: string, _value: string) => {}, flush: async () => {} };
