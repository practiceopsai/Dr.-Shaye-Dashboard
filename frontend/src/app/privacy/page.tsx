import Link from 'next/link';

export const metadata = { title: 'Privacy | Eli Command Center' };
export default function Privacy() {
  return <main style={{ maxWidth: 740, margin: '0 auto', padding: '56px 24px', lineHeight: 1.75 }}>
    <Link href="/">← Eli Command Center</Link>
    <h1>Privacy in Eli Command Center</h1>
    <p>Updated September 14, 2026. Eli Command Center is a private operations application for Dr. Shaye and his authorized chief of staff.</p>
    <h2>Account and operational information</h2>
    <p>Google verifies your sign-in. The server checks your verified email against its approved accounts. Your name, email, and account role identify access and attribute requests. The app displays priorities, calendar information, and Eli’s system status from the existing connected services.</p>
    <h2>Requests, feedback, and dictation</h2>
    <p>Requests and feedback you submit are sent to the Eli backend and recorded in Eli’s operations system. If delivery to Eli is temporarily unavailable, the backend stores pending requests for retry. Sent information can be processed by the connected AI and automation services that operate Eli, including Anthropic, Composio, and the hosted Eli environment.</p>
    <p>On iPhone, dictation starts only when you select it and grant permission. Speech recognition uses the operating system’s speech service and may process audio through Apple. You can edit the transcript before sending it. The command center receives the submitted text, not an audio recording from the app.</p>
    <h2>Information on your phone</h2>
    <p>Native Google sign-in manages credentials through its iOS SDK. Unsent drafts are stored using iOS Keychain storage, separately for each approved account. Dashboard information is held in application memory and refreshed from the server. Signing out clears the visible session; saved drafts remain available to the same account on that phone.</p>
    <h2>App delivery and analytics</h2>
    <p>Expo provides app builds and compatible software updates. Apple provides TestFlight and App Store distribution. These providers may receive technical information needed to deliver and operate their services. The app includes no advertising SDK and requests no advertising tracking permission.</p>
    <h2>Access and removal requests</h2>
    <p>The app uses existing approved Workspace accounts and does not create a separate public account. To request access removal, correction, deletion of command-center records, or help with a privacy issue, contact <a href="mailto:fabio@practiceops.ai">fabio@practiceops.ai</a>. Operational records remain in the connected systems until removed under their retention processes.</p>
    <p>Please keep patient-identifiable information out of the command center. It is an operations tool, not a clinical record system.</p>
    <Link href="/support">Contact support</Link>
  </main>;
}
