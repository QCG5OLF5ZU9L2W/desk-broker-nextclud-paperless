// Test data only; pdf-lib is not included in the extension.
const path = require('node:path'), fs = require('node:fs');
const {PDFDocument, StandardFonts, rgb} = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
  ? path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'pdf-lib') : 'pdf-lib');
(async () => {
  const pdf = await PDFDocument.create(), font = await pdf.embedFont(StandardFonts.Helvetica);
  for (let number = 1; number <= 3; number++) {
    const page = pdf.addPage([420, 595]);
    page.drawRectangle({x: 0, y: 0, width: 420, height: 595,
      color: rgb(number === 1 ? .9 : .6, number === 2 ? .9 : .6, number === 3 ? .9 : .6)});
    page.drawText('PAGE ' + number, {x: 50, y: 300, font, size: 32});
  }
  fs.writeFileSync(process.argv[2], await pdf.save());
})().catch(error => {console.error(error); process.exitCode = 1;});
