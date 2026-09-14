// Browser rendering is only for layout review. Google login requires the signed iOS build.
export async function signIn(): Promise<boolean> { throw new Error('Install the iPhone app to sign in.'); }
export async function restore() { return false; }
export async function getToken(): Promise<string> { throw new Error('Native Google sign-in is required.'); }
export async function signOut() {}
