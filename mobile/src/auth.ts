import { GoogleSignin } from '@react-native-google-signin/google-signin';
import * as SecureStore from 'expo-secure-store';
import { config, loginConfigured } from './config';

// The native Google SDK keeps refresh credentials in the iOS Keychain. Never
// persist ID/access tokens in AsyncStorage, the JS bundle, or application logs.
if (loginConfigured) GoogleSignin.configure({ webClientId: config.webClientId, iosClientId: config.iosClientId });

let generation = 0;
let tokenRequest: Promise<string> | null = null;
export async function signIn() {
  if (!loginConfigured) throw new Error('Google sign-in has not been configured for this build.');
  const response = await GoogleSignin.signIn();
  if (response.type === 'success') await SecureStore.deleteItemAsync('eli.signed-out');
  return response.type === 'success';
}
export async function restore() {
  if (!loginConfigured || await SecureStore.getItemAsync('eli.signed-out') || !GoogleSignin.hasPreviousSignIn()) return false;
  const response = await GoogleSignin.signInSilently();
  return response.type === 'success';
}
export function getToken(): Promise<string> {
  if (!tokenRequest) {
    const started = generation;
    tokenRequest = GoogleSignin.getTokens().then(tokens => {
      if (generation !== started) throw new Error('Session ended.');
      return tokens.idToken;
    }).finally(() => { tokenRequest = null; });
  }
  return tokenRequest;
}
export async function signOut() {
  generation++;
  // A failed Google network sign-out must not restore the session on relaunch.
  await SecureStore.setItemAsync('eli.signed-out', 'true', { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  await GoogleSignin.signOut();
}
