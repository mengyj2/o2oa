# 用 Excel COM 真机验证生成的 .xlsx
# 逐个 Open -> 回读工作表名/单元格 -> Close，任何异常都记录
$dir = "D:\O2OA\o2oa高级应用开发\deliverables\_excel"
$out = "D:\O2OA\o2oa高级应用开发\build\_excel_verify.txt"
$r = @()

$xl = $null
try {
    $xl = New-Object -ComObject Excel.Application
} catch {
    Set-Content -Path $out -Value ("FATAL Excel COM 无法创建: " + $_.Exception.Message) -Encoding UTF8
    return
}
$xl.Visible = $false
$xl.DisplayAlerts = $false
$r += "Excel Version = " + $xl.Version

$files = Get-ChildItem $dir -Filter *.xlsx | Sort-Object Name
$ok = 0; $bad = 0
foreach ($f in $files) {
    $wb = $null
    try {
        $wb = $xl.Workbooks.Open($f.FullName, 0, $true)   # ReadOnly
        $sheetCount = $wb.Worksheets.Count
        $names = @()
        foreach ($ws in $wb.Worksheets) { $names += $ws.Name }

        # 回读数据页第 1/2 行前 3 列，确认真有内容
        $dataName = $names[$names.Count - 1]
        $dws = $wb.Worksheets.Item($dataName)
        $h1 = [string]$dws.Cells.Item(1,1).Text
        $h2 = [string]$dws.Cells.Item(1,2).Text
        $t1 = [string]$dws.Cells.Item(2,1).Text
        $used = $dws.UsedRange.Rows.Count
        $cols = $dws.UsedRange.Columns.Count
        $frozen = $dws.Application.ActiveWindow.FreezePanes
        $r += ("OK   {0} | sheets={1} | data='{2}' | hdr=[{3}|{4}] | sub='{5}' | rows={6} cols={7}" -f `
               $f.Name, $sheetCount, $dataName, $h1, $h2, $t1, $used, $cols)
        $ok++
        $wb.Close($false)
    } catch {
        $r += ("FAIL {0} | {1}" -f $f.Name, $_.Exception.Message)
        $bad++
        if ($wb) { try { $wb.Close($false) } catch {} }
    }
}
$r += ("===== 合计 {0} 个：成功 {1}，失败 {2} =====" -f $files.Count, $ok, $bad)
$xl.Quit()
[void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
Set-Content -Path $out -Value $r -Encoding UTF8
