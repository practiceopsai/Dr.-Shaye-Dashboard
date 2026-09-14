import { GoogleSignin } from '@react-native-google-signin/google-signin';
import * as SecureStore from 'expo-secure-store';
import * as auth from '../src/auth';
jest.mock('@react-native-google-signin/google-signin', () => ({ GoogleSignin: { configure: jest.fn(), hasPreviousSignIn: jest.fn().mockReturnValue(true), signInSilently: jest.fn().mockResolvedValue({ type: 'success' }), signIn: jest.fn().mockResolvedValue({ type: 'success' }), getTokens: jest.fn().mockResolvedValue({ idToken: 'token' }), signOut: jest.fn() } }));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(), setItemAsync: jest.fn(), deleteItemAsync: jest.fn(), WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'device-only' }));
beforeEach(() => { jest.clearAllMocks(); });
test('a saved sign-out marker prevents silent restoration', async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue('true');
  expect(await auth.restore()).toBe(false);
  expect(GoogleSignin.signInSilently).not.toHaveBeenCalled();
});
test('records local sign-out before calling Google', async () => {
  jest.mocked(GoogleSignin.signOut).mockRejectedValueOnce(new Error('network error'));
  await expect(auth.signOut()).rejects.toThrow('network error');
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith('eli.signed-out', 'true', { keychainAccessible: 'device-only' });
});
test('explicit successful sign-in clears the sign-out marker', async () => {
  expect(await auth.signIn()).toBe(true);
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('eli.signed-out');
});
test('coalesces concurrent SDK token refresh requests', async () => {
  await expect(Promise.all([auth.getToken(), auth.getToken()])).resolves.toEqual(['token', 'token']);
  expect(GoogleSignin.getTokens).toHaveBeenCalledTimes(1);
});
