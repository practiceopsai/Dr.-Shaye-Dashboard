# Eli for iPhone

Native React Native / Expo SDK 57 app for the existing Eli command center. Requires iOS 16.4 or later. Distribution uses TestFlight, followed by the App Store if desired. Expo Go cannot run the native Google sign-in module.

## Product

- Today: current ranked priorities and the next calendar items.
- Schedule: dated calendar entries and priority deadlines in the principal’s timezone.
- Work: commitments across Now, Protect, Delegate, and Monitor, including P4 administration.
- Decide: current Now-lane items with exact action review before approval.
- Eli: dated behavioral stage, shared memory, authority levels, health, sources, and connections.
- Requests and feedback: native dictation with permission handling, editable transcripts, account-specific encrypted drafts, delivery receipts, and explicit uncertain outcomes.

Only the backend’s approved Google Workspace users can sign in. Native Google sign-in obtains ID tokens for the existing web/server audience. The phone contains public client identifiers, never Composio, Orgo, Anthropic, or backend service credentials.

The login screen also offers **Preview with sample data**. It uses the same screens with fictional, disposable data and an isolated client that makes no API requests. A persistent banner identifies sample mode, including in request and approval sheets. Sample receipts never claim a real external action. Exit the preview to sign in to the private command center.

## Development and verification

Use Node 24 (minimum 22.13). From this directory:

```sh
npm ci
npm run typecheck
npm test
node scripts/sync-contract.cjs --check
npm run release:check
npm run export:ios -- --max-workers 2
npx expo start --dev-client
```

`release.json` contains public production identifiers. `.env.local` can override them locally; `.env.example` documents the supported keys. API types are synchronized from the existing frontend contract by `node scripts/sync-contract.cjs`. CI detects contract drift.

An exported JavaScript/Hermes bundle is a validation artifact. An installable iPhone application additionally needs an Apple-signed native build.

The native iOS simulator build for source `c2d145a` passed on September 14, 2026: [EAS build](https://expo.dev/accounts/fvarenss-team/projects/fabio/builds/2a8edc99-cc55-4dae-93fe-ec9dabceba11). The first signed production build, version 1.0.0 (2), also passed: [production build](https://expo.dev/accounts/fvarenss-team/projects/fabio/builds/8909fcf8-d96b-446a-bb0c-fea47d94fce3). Its TestFlight upload has been scheduled. Sample mode requires the subsequent build; actual-device acceptance and Apple's external beta review remain pending.

## Ownership and release

- Expo project: `@fvarenss-team/fabio`, ID `3f3cfa91-36a6-4b87-9971-c8efe09e5f3e`. The existing Expo project slug is retained; the installed app name is **Eli Command Center**.
- Apple team: `2VY2A3RWFV`.
- Bundle identifier: `ai.practiceops.eli`.
- App Store Connect app ID: `6811994794`.
- Production API: `https://backend-production-b5792.up.railway.app`.

One-time login and managed signing setup:

```sh
npx eas-cli@latest login --no-browser
npx eas-cli@latest credentials:configure-build --platform ios --profile production
```

Apple signing is configured through the Team App Store Connect API key route. EAS holds the distribution certificate, provisioning profile, and submission API key in managed credentials. Keep downloaded `.p8` files private and outside this repository. Windows is supported for the cloud build/release workflow; a local Mac is not required.

Build and submit:

```sh
npx eas-cli@latest build --platform ios --profile production
npx eas-cli@latest submit --platform ios --profile production --id <finished-build-id> --no-auto-testflight-setup
```

The `Build iPhone for TestFlight` GitHub workflow performs checks before building, then submits that exact finished build. The Expo automation token is configured in the `EXPO_TOKEN` repository secret. Managed iOS signing and App Store Connect submission credentials are configured. Automatic TestFlight group creation is disabled so release automation does not invite every App Store Connect administrator. Tester enrollment is managed separately.

## Fresh data and software updates

The app reloads on foreground, network recovery, pull-to-refresh, successful mutation, and every minute while active. The server’s `generated_at`, `expires_at`, and principal timezone govern freshness. Expired or unavailable data cannot be approved. The backend prepares daily briefs independently of iOS background execution.

EAS Update is enabled on the production channel with fingerprint-based runtime matching. Compatible updates download at startup and apply on a later safe restart. Account settings also allow an explicit update check. Drafts are flushed before a requested restart. No update is applied during an approval or active composer.

```sh
npx eas-cli@latest update --channel production --platform ios --environment production --message "Describe the compatible app change"
```

The `Publish compatible iPhone update` workflow automatically publishes successful native-app checks for pushes to this repository’s main branch. It publishes the exact verified commit and does not accept pull-request or fork runs. Native dependency/configuration changes produce a different runtime and require a new Apple-signed build. TestFlight/App Store automatic updates depend on the user’s Apple settings. Optional end-to-end EAS Update signing can be configured with `certs/update-certificate.pem`; its private key belongs outside this repository. Expo currently restricts that extra signing feature to paid Production/Enterprise plans. Standard updates use Expo’s authenticated publishing and HTTPS delivery.

## Device acceptance before broad distribution

Check both approved accounts, rejection of an unapproved account, expired Google credentials, foreground after local midnight, offline recovery, voice permission denied, saved-draft restoration, exact approval details, ambiguous delivery, and real Google sign-in on two iPhones. Verify the TestFlight native build separately from JavaScript export and mocked component tests.

The request API provides capture receipts, not a conversational reply. A request to change the app becomes tracked work for Eli; it does not itself publish code. External actions remain governed by the backend’s approval and execution policy.

Privacy: https://eli-commandcenter.up.railway.app/privacy

Support: https://eli-commandcenter.up.railway.app/support
