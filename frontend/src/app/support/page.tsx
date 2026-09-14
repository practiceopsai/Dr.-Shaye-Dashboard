import Link from 'next/link';

export const metadata = { title: 'Support | Eli Command Center' };
export default function Support() {
  return <main style={{ maxWidth: 740, margin: '0 auto', padding: '56px 24px', lineHeight: 1.75 }}>
    <Link href="/">← Eli Command Center</Link><h1>Eli support</h1>
    <p>For access, installation, account removal, or a problem with Eli Command Center, contact <a href="mailto:fabio@practiceops.ai">fabio@practiceops.ai</a>.</p>
    <h2>Sign-in</h2><p>Use your approved Google Workspace account. Access is restricted to Dr. Shaye and his authorized chief of staff. If your session expires, sign in again.</p>
    <h2>Fresh information</h2><p>Pull down to refresh the iPhone app. Briefs refresh while the app is active and when it returns to the foreground. If the phone is offline or the brief expires, actions are hidden until current information can be loaded.</p>
    <h2>Requests and approvals</h2><p>A recorded or queued receipt confirms that a request was captured. It does not mean an external action has completed. If delivery is uncertain, check the outcome before sending the same request again.</p>
    <h2>App updates</h2><p>Eli’s data updates through the shared backend. Compatible app updates may download for the next restart. Native changes arrive through TestFlight or the App Store. You can enable automatic updates in the distribution app.</p>
    <Link href="/privacy">Privacy information</Link>
  </main>;
}
