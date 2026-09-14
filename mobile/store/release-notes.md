# Eli Command Center 1.0

Your priorities, schedule, commitments, and Eli’s current state in one private iPhone application.

This first release includes native Google Workspace sign-in, current priority ranking, behavior and memory status, authority levels, exact action review, voice dictation, encrypted drafts, and automatic brief refresh.

## What to test

Sign in with your approved Workspace account. Pull down to refresh Today, check Schedule and Eli status, submit a non-sensitive request, and confirm that closing/reopening the app preserves an unsent draft. Check that denied microphone permission still permits typing.

Without a production account, tap **Preview with sample data** on the login screen. Explore all five tabs, capture a sample request, provide feedback, and approve a sample decision. The banner and receipts identify the preview; it makes no requests to Eli and performs no external actions.

An approval receipt that says “queued” is not confirmation of external execution. Requests receive capture receipts rather than a live chat reply.

## App Review context

This application serves an existing private business workflow. Access is restricted server-side to two existing Google Workspace accounts. It does not create consumer accounts, sell subscriptions, or provide clinical advice. Google sign-in authenticates those existing business identities. All external action approvals show account, recipients, and arguments before confirmation.

Review access: tap **Preview with sample data** on the login screen. No credentials are needed. The visible preview exercises the app's screens with fictional data and isolated in-memory requests, feedback, and approvals. It is available to every user and can be exited at any time. Production data contains private business information and remains restricted to the approved Workspace accounts. Review notes should request acceptance of this demo arrangement; Apple may require additional access. No review bypass is present in the production API. Submit a binary that includes sample mode, rather than relying on a downloaded update to add it.

Privacy URL: https://eli-commandcenter.up.railway.app/privacy

Support URL: https://eli-commandcenter.up.railway.app/support
