# Fonts

`NotoSansSC-Regular.ttf` and `NotoSansSC-Bold.ttf` are static instances (weights 400 and
700) of Google's variable font Noto Sans SC, embedded in quote and proforma PDFs because
the documents mix Chinese and Latin text.

- Source: https://github.com/google/fonts/blob/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf
  (sha256 a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da), 2026-10-04
- Licence: SIL Open Font License 1.1, see `OFL.txt`
- Made with fontTools: `instancer.instantiateVariableFont(font, {"wght": 400 | 700})`

Static files load in a fraction of a second; instancing the variable font took about 20 s
per document.
