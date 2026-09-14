import release from '../release.json';
export const config = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL || release.apiUrl,
  webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || release.googleWebClientId,
  iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || release.googleIosClientId,
  supportUrl: 'https://eli-commandcenter.up.railway.app/support',
  privacyUrl: 'https://eli-commandcenter.up.railway.app/privacy',
};

export const loginConfigured = Boolean(config.webClientId && config.iosClientId);
