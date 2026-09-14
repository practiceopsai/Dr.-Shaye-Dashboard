# Eli Command Center 1.0

Your priorities, schedule, commitments, and Eli’s current state in one private iPhone application.

This first release includes native Google Workspace sign-in, current priority ranking, behavior and memory status, authority levels, exact action review, voice dictation, encrypted drafts, and automatic brief refresh.

## What to test

Sign in with your approved Workspace account. Pull down to refresh Today, check Schedule and Eli status, submit a non-sensitive request, and confirm that closing/reopening the app preserves an unsent draft. Check that denied microphone permission still permits typing.

An approval receipt that says “queued” is not confirmation of external execution. Requests receive capture receipts rather than a live chat reply.

## App Review context

This application serves an existing private business workflow. Access is restricted server-side to two existing Google Workspace accounts. It does not create consumer accounts, sell subscriptions, or provide clinical advice. Google sign-in authenticates those existing business identities. All external action approvals show account, recipients, and arguments before confirmation.

An authorized review-access arrangement must be supplied in App Store Connect before beta review; do not submit either user’s private credentials in this public repository. No review bypass is present in the production API.

Privacy URL: https://eli-commandcenter.up.railway.app/privacy

Support URL: https://eli-commandcenter.up.railway.app/support
