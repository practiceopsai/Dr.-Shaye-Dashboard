# Eli for iPhone: TestFlight first

Decision recorded September 14, 2026: distribute through TestFlight or the App Store. A Safari Home Screen installation is not the chosen release route.

Implementation update, September 14, 2026: the native application exists in `mobile/`, with 29 passing tests, TypeScript and contract checks, iOS export, and successful native compilation. Signed production version 1.0.0 (5), build `7adc20c7-873e-4569-bcf2-0016080ca830`, includes the visible sample preview and required privacy metadata. **Apple validated the build, enabled internal TestFlight testing, and accepted the account holder's invitation request.** External beta review is `WAITING_FOR_REVIEW`; the limited sharing link is kept private. The account holder confirmed that installation and live iPhone access work. Dr. Shaye is enrolled as an external tester; Apple currently blocks the invitation because no externally installable build is approved. Automatic tester notification is enabled for the pending review. The production update service returns a manifest matching the signed app's embedded runtime; Windows/CI line endings are normalized to preserve this compatibility. Privacy and support pages are deployed. See `mobile/README.md` for release commands.

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
5. Upload the signed build to TestFlight. Invite the account holder at the explicitly confirmed email. Prepare a limited external beta link for sharing with Dr. Shaye after Apple's beta review; do not enroll an external tester as a developer just to avoid review.
6. Gather acceptance feedback, then choose App Store distribution appropriate to the intended audience. Maintain the allowlist even if the app listing becomes public. Prepare privacy disclosures, review instructions, support information, and account/access management.

## Signing and distribution status

- Apple Developer membership, agreements, app record, managed signing credentials, and submission API key are configured. The supported API-key route resolved the earlier password-based signing failure.
- Bundle identifier `ai.practiceops.eli` and the dedicated iOS OAuth client have been configured in the existing Google project.
- Expo ownership is `fvarenss-team`, project `fabio`. The account, public app identifiers, update channels, and GitHub automation secret are configured.
- The account holder confirmed successful iPhone access. Dr. Shaye is enrolled in the external beta group. Apple rejected the immediate email invitation with `STATE_ERROR.TESTER_INVITE.NO_INSTALLABLE_BUILDS`; automatic tester notification is enabled for release after beta approval. The limited sharing link remains available as an alternative after approval.

The signed release uses Apple's documented Build Uploads API after redundant EAS submissions were canceled during a queue delay. TestFlight builds expire after 90 days, so release maintenance is required even during a private beta. Actual-device acceptance and Apple's beta review remain separate from JavaScript export and unit/component tests. The sample preview is visible to everyone and uses fictional data without granting access to production services.

## Primary references

- [Expo: native Google authentication](https://docs.expo.dev/guides/google-authentication/)
- [Expo: update runtime compatibility](https://docs.expo.dev/eas-update/runtime-versions/)
- [Apple: TestFlight distribution](https://developer.apple.com/testflight/)
- [Apple: TestFlight build lifetime and updates](https://testflight.apple.com/)
- [Apple: App Review Guidelines, including 2.5.2 and login requirements](https://developer.apple.com/app-store/review/guidelines/)
