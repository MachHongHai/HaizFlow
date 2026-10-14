# edge-tts

HFlow uses the unmodified edge-tts 7.3.1 Python client by rany.

- Upstream: https://github.com/rany2/edge-tts
- Pinned source: https://github.com/rany2/edge-tts/tree/360fa8e1de354e1dda74c09bd695887d6a44df74
- Source distribution: https://codeload.github.com/rany2/edge-tts/tar.gz/360fa8e1de354e1dda74c09bd695887d6a44df74
- License: GNU Lesser General Public License version 3; the exact wheel license
  is copied by the release dependency-notice generator. The repository also
  retains `LGPL-3.0.txt` and `GPL-3.0.txt` in this directory.

The packaging hook retains the upstream package as plain Python source modules,
not a private embedded replacement. In a standalone local copy, its modules in
`_internal/edge_tts/` can be inspected and replaced. Refer to
`docs/third-party-library-replacement.md` for using modified standalone copies
without an official installer replacing them. Future frozen releases must test
this replacement path before publication; no such binary was built in this
source-only change.

HFlow's adapter and retry policy are independent code. No Microsoft service
credentials, endpoint tokens or signing implementation are copied into them.
The client's LGPL license is not a grant of Microsoft service access or output
rights. Those terms must be considered separately for the intended use.
