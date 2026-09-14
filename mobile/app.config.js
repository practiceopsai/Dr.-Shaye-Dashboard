const release = require('./release.json');
const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID || release.projectId;
const iosClientId = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || release.googleIosClientId;
const fs = require('node:fs');
const signedUpdates = fs.existsSync('./certs/update-certificate.pem');

module.exports = {
  expo: {
    name: 'Eli Command Center',
    slug: 'fabio',
    owner: process.env.EXPO_OWNER || release.owner,
    version: '1.0.0',
    scheme: 'elicommandcenter',
    orientation: 'portrait',
    userInterfaceStyle: 'light',
    icon: './assets/eli-icon.png',
    platforms: ['ios', 'web'],
    ios: {
      bundleIdentifier: process.env.IOS_BUNDLE_IDENTIFIER || release.bundleIdentifier,
      appleTeamId: process.env.APPLE_TEAM_ID || release.appleTeamId,
      supportsTablet: false,
      infoPlist: { ITSAppUsesNonExemptEncryption: false },
    },
    plugins: [
      'expo-secure-store',
      ['expo-splash-screen', { backgroundColor: '#234d3c', image: './assets/eli-splash.png', imageWidth: 160 }],
      ['expo-speech-recognition', {
        microphonePermission: 'Eli uses your microphone only when you choose to dictate a request.',
        speechRecognitionPermission: 'Convert your spoken request to text so you can review it before sending to Eli.',
      }],
      ...(iosClientId ? [['@react-native-google-signin/google-signin', {
        iosUrlScheme: iosClientId.split('.').reverse().join('.'),
      }]] : []),
    ],
    runtimeVersion: { policy: 'fingerprint' },
    updates: {
      enabled: Boolean(projectId),
      ...(projectId ? { url: `https://u.expo.dev/${projectId}` } : {}),
      checkAutomatically: 'ON_LOAD',
      fallbackToCacheTimeout: 0,
      ...(signedUpdates ? {
        codeSigningCertificate: './certs/update-certificate.pem',
        codeSigningMetadata: { keyid: 'eli-production', alg: 'rsa-v1_5-sha256' },
      } : {}),
    },
    extra: { ...(projectId ? { eas: { projectId } } : {}) },
    web: { favicon: './assets/eli-favicon.png', bundler: 'metro' },
  },
};
