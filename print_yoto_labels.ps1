param(
    [Parameter(Mandatory = $true)][string]$Pdf,
    [Parameter(Mandatory = $true)][string]$Printer,
    [Parameter(Mandatory = $true)][string]$Tray,
    [string]$Python = 'python',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$pdfPath = (Resolve-Path -LiteralPath $Pdf).Path
$renderFolder = Join-Path ([IO.Path]::GetTempPath()) ('yoto-print-' + [guid]::NewGuid().ToString('N'))
$document = [System.Drawing.Printing.PrintDocument]::new()
try {
    $document.PrinterSettings.PrinterName = $Printer
    if (-not $document.PrinterSettings.IsValid) { throw "Printer is unavailable: $Printer" }
    $a4 = $document.PrinterSettings.PaperSizes | Where-Object Kind -eq A4 | Select-Object -First 1
    if (-not $a4) { throw 'This printer does not advertise A4 paper' }
    $paperTray = $document.PrinterSettings.PaperSources | Where-Object SourceName -eq $Tray | Select-Object -First 1
    if (-not $paperTray) {
        $available = ($document.PrinterSettings.PaperSources | ForEach-Object SourceName) -join ', '
        throw "Unknown tray '$Tray'. Available trays: $available"
    }
    $printerState = Get-CimInstance Win32_Printer | Where-Object Name -eq $Printer | Select-Object -First 1
    if (-not $DryRun) {
        if ($printerState.WorkOffline) { throw 'Printer is offline' }
        if ($printerState.DetectedErrorState -eq 4) { throw 'Printer reports no paper. Load the selected A4 tray first.' }
    }
    New-Item -ItemType Directory -Path $renderFolder | Out-Null
    $renderCode = @'
import sys
from pathlib import Path
import pymupdf
with pymupdf.open(sys.argv[1]) as doc:
    if not len(doc):
        raise ValueError('PDF is empty')
    for index, page in enumerate(doc):
        if abs(page.rect.width - 595.276) > 1 or abs(page.rect.height - 841.890) > 1:
            raise ValueError('Only portrait A4 PDFs can be printed at actual size')
        page.get_pixmap(dpi=300, alpha=False).save(Path(sys.argv[2]) / f'{index:04d}.png')
'@
    & $Python -c $renderCode $pdfPath $renderFolder
    if ($LASTEXITCODE -ne 0) { throw 'Could not render the A4 label PDF; install requirements-yoto.txt' }
    $pages = @(Get-ChildItem -LiteralPath $renderFolder -Filter '*.png' | Sort-Object Name)
    if ($pages.Count -eq 0) { throw 'No PDF pages rendered' }
    $document.DocumentName = [IO.Path]::GetFileNameWithoutExtension($pdfPath) + ' (actual size)'
    $document.PrinterSettings.Copies = 1
    $document.PrinterSettings.Duplex = [System.Drawing.Printing.Duplex]::Simplex
    $document.DefaultPageSettings.PaperSize = $a4
    $document.DefaultPageSettings.PaperSource = $paperTray
    $document.DefaultPageSettings.Landscape = $false
    $document.DefaultPageSettings.Margins = [System.Drawing.Printing.Margins]::new(0, 0, 0, 0)
    $document.PrintController = [System.Drawing.Printing.StandardPrintController]::new()
    $pageState = @{ Index = 0 }
    $document.add_PrintPage({
        param($sender, $eventArgs)
        $pageImage = [System.Drawing.Image]::FromFile($pages[$pageState.Index].FullName)
        try {
            $eventArgs.Graphics.PageUnit = [System.Drawing.GraphicsUnit]::Display
            $eventArgs.Graphics.DrawImage($pageImage,
                [single](-$eventArgs.PageSettings.HardMarginX),
                [single](-$eventArgs.PageSettings.HardMarginY),
                [single](210 / 25.4 * 100), [single](297 / 25.4 * 100))
            $pageState.Index++
            $eventArgs.HasMorePages = $pageState.Index -lt $pages.Count
        } finally { $pageImage.Dispose() }
    })
    if ($DryRun) {
        Write-Output "Dry run: $($pages.Count) A4 page(s), 100% actual size, printer '$Printer', tray '$Tray'. Nothing printed."
    } else {
        $document.Print()
        Write-Output "Submitted $($pages.Count) A4 page(s) at actual size to '$Printer', tray '$Tray'. Check the physical sheet; queue submission is not proof of printing."
    }
} finally {
    $document.Dispose()
    if (Test-Path -LiteralPath $renderFolder) {
        # This helper creates a flat directory containing only rendered PNGs.
        Get-ChildItem -LiteralPath $renderFolder -Filter '*.png' -File | Remove-Item -Force
        Remove-Item -LiteralPath $renderFolder
    }
}
