# Tests of a local server: free port, queue size, page-load burst

Run 27 lost about an hour of the Test phase to two flaky failures that had app causes the Build phase could have caught:
a test failed with "Port 60013 is in use by another program", and the board sometimes loaded without one of its scripts.
The second was a real server bug: a stdlib `http.server`-based server keeps a listen queue of 5, and a page that asks for
about ten files at once had some of them turned away. With the queue raised, 10 of 10 browser runs passed (6 of 8 without).

Three rules for every section that starts or changes a local server:

1. **A test never names a port.** It binds port `0` (or asks the OS for a free one), reads the port back and passes it on.
   A literal port in a test file is a flaky test waiting for another program. The lifecycle test of a "port in use" case
   holds a port itself, on a free one it just took, and never relies on a fixed number being busy or free.
2. **The server sets its listen queue.** A server built on `socketserver` / `http.server` sets `request_queue_size`
   (at least 64) on its server class; other stacks set the equivalent backlog. A page that loads many files at once must not
   depend on the default.
3. **A burst test loads the real page many times at once.** One test starts the server, opens the board page in a browser
   (or requests the page and all its assets in parallel, 10 times over) and asserts that every asset arrived. This is the
   test that failed intermittently in run 27; written in the section that builds the server, it fails the first time instead
   of one time in ten.

The code reviewer rejects a test with a literal port, and a server class that leaves the listen queue at its default while
serving a page with several assets.
