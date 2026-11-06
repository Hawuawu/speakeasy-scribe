`SpeakEasy_Db.lua` is copied unchanged from [FinMckinnon/speak-easy](https://github.com/FinMckinnon/speak-easy)
(commit `67072258019692239d6f8468d66e062759d688de`, MIT licensed, see `LICENSE` here).
`tests/test_upstream.py` runs SpeakEasy's own load-time clean-up (`L.Db.Load`) on files written by
speakeasy-scribe, to prove the addon keeps every scene, line, trigger and wheel slot unchanged.
Refresh it when SpeakEasy changes its data format.
