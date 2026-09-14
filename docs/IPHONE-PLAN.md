# Eli for iPhone: TestFlight first

Decision recorded September 14, 2026: distribute through TestFlight or the App Store. A Safari Home Screen installation is not the chosen release route.

Implementation update, September 14, 2026: the native application now exists in `mobile/`, with targeted tests, a successful iOS JavaScript export, and GitHub verification. The native iOS simulator build also compiled successfully on EAS (build `2a8edc99-cc55-4dae-93fe-ec9dabceba11`, source `c2d145a`). Production EAS updates are connected to successful checks on main and have published successfully. Privacy and support pages are deployed. Apple signing and App Store Connect submission remain outstanding; no installable TestFlight release has been published yet. See `mobile/README.md` for the implemented app and release commands.

## Architecture

The React Native / Expo SDK 57 application uses the existing FastAPI backend and its typed dashboard contract. It includes native Today, Schedule, Commitments, Decisions, Eli status, and request/feedback screens. The phone contains no Orgo, Anthropic, Composio, or AgentMail secrets. There is one production Eli vault and one set of priorities for both authorized users.

Use native Google Sign-In, with the existing server-side email allowlist and verified Google ID tokens. Configure a dedicated iOS OAuth client and server audience deliberately; never bypass audience verification or broaden the allowed users to make mobile login work. Refresh credentials through the Google SDK; store any app session material in the iOS Keychain. Keep operator feedback distinct from principal preferences. Sign-out clears in-memory private content.

Use the server's generated_at, expires_at, timezone, and dated source metadata. Reload on foreground, network recovery, manual refresh, and after a mutation. Hide expired actions. An offline phone displays an explicit unavailable state. iOS background execution is not required for freshness: the backend prepares each day's brief and refreshes when the app is used.

## What updates automatically

| Change | Delivery |
|---|---|
| Eli memory, behavior, familiarity, authority, tasks and calendar | Existing server APIs; visible after the next successful refresh |
| Priority synthesis, API integrations and server fixes | Tested backend deployment; no phone reinstall |
| Existing compatible JavaScript/assets | EAS Update after successful GitHub verification, within the matching native runtime and Apple's rules; activate on a safe restart, preserving drafts. Extra end-to-end signing is optional and requires a qualifying Expo plan |
| Native modules, permissions, capabilities or significant new functionality | New signed iOS build through TestFlight/App Store; users may enable automatic updates |

Do not promise that every native feature can be silently replaced. Runtime compatibility and Apple review requirements still apply. Backend policy remains authoritative regardless of the installed client version.

## Release sequence

1. Finish and verify the shared API, dated status, daily refresh, persistent internal writeback, and account-specific attribution. Maintain backwards-compatible API fields.
2. Create the native app with the screens above, native Google sign-in, pull-to-refresh, accessibility, safe-area layouts, and foreground refresh. The initial request screen captures requests; it must not imply a conversational reply from Eli where the API only confirms recording.
3. Configure the Apple Developer team, bundle identifier, App Store Connect record, iOS Google OAuth client, and Expo/EAS project. Keep signing credentials and API keys in managed secret storage. Use development, preview, and production build profiles with separate update channels.
4. Test on two actual iPhones: both allowed logins, rejected third account, token expiry, foreground after midnight, network loss, API failure, pagination, voice permission denied, feedback while Eli is unavailable, restart recovery, draft preservation, and exact-action approvals.
5. Upload the first signed build to TestFlight. Invite the two intended testers explicitly after confirming their Apple account emails. External testing requires Apple's beta review; do not enroll a tester as a developer just to avoid review.
6. Gather acceptance feedback, then choose App Store distribution appropriate to the intended audience. Maintain the allowlist even if the app listing becomes public. Prepare privacy disclosures, review instructions, support information, and account/access management.

## Signing and distribution status

- Apple Developer membership and team have been provided. App Store Connect signing access is being configured. EAS CLI's removed Apple service-key endpoint currently prevents its password-based setup; the supported API-key route is the planned alternative.
- Bundle identifier `ai.practiceops.eli` and the dedicated iOS OAuth client have been configured in the existing Google project.
- Expo ownership is `fvarenss-team`, project `fabio`. The account, public app identifiers, update channels, and GitHub automation secret are configured.
- Tester Apple account emails and invitation authorization are still needed if distribution uses individual invitations rather than a shareable beta link.

No Apple membership purchase, app submission, or tester invitation has been made. TestFlight builds expire after 90 days, so release maintenance is required even during a private beta. Actual-device acceptance and Apple's beta review remain separate from JavaScript export and unit/component tests.

## Primary references

- [Expo: native Google authentication](https://docs.expo.dev/guides/google-authentication/)
- [Expo: update runtime compatibility](https://docs.expo.dev/eas-update/runtime-versions/)
- [Apple: TestFlight distribution](https://developer.apple.com/testflight/)
- [Apple: TestFlight build lifetime and updates](https://testflight.apple.com/)
- [Apple: App Review Guidelines, including 2.5.2 and login requirements](https://developer.apple.com/app-store/review/guidelines/)
