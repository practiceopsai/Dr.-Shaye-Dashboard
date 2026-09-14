const { load } = require('@expo/env');
load(process.cwd());
const config = require('../app.config.js').expo;
const release = require('../release.json');
const clients = { EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || release.googleWebClientId, EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || release.googleIosClientId };
const problems = [];
for (const name of ['EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID', 'EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID']) {
  if (!/^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$/.test(clients[name] || '')) problems.push(`${name} must be a real Google OAuth client ID.`);
}
if (clients.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID === clients.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID) problems.push('Use separate web and iOS Google OAuth clients.');
if (!config.extra?.eas?.projectId) problems.push('Link the app to its EAS project.');
if (!config.ios.appleTeamId) problems.push('Set the Apple Developer Team ID.');
const api = process.env.EXPO_PUBLIC_API_URL || 'https://backend-production-b5792.up.railway.app';
if (new URL(api).origin !== 'https://backend-production-b5792.up.railway.app') problems.push('Production must use the verified Eli backend.');
if (problems.length) { console.error('iPhone release configuration is incomplete:\n' + problems.map(value => `- ${value}`).join('\n')); process.exit(1); }
console.log(`Release configuration verified: ${config.ios.bundleIdentifier}, Apple team ${config.ios.appleTeamId}.`);
