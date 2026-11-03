param([switch]$Force)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Destination = Join-Path $Root 'src/haizflow/assets/fonts'
$Licenses = Join-Path $Root 'licenses'
$IndexPath = Join-Path $Root 'src/haizflow/assets/subtitle-fonts.json'
$Index = if (Test-Path -LiteralPath $IndexPath) { Get-Content -LiteralPath $IndexPath -Raw | ConvertFrom-Json } else { $null }
$Noto = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
$Google = '2fe1e8c6b137fb13041a7cfca6fdcd8a910ea4dc'
$Pretendard = '7aeb0698819be2b4097dae8ec8fe6a795e5cf3ae'
$Assets = @(
    @{ Name='NotoSansSC-Black.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/SubsetOTF/SC/NotoSansSC-Black.otf" },
    @{ Name='NotoSansTC-Black.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/SubsetOTF/TC/NotoSansTC-Black.otf" },
    @{ Name='NotoSansJP-Black.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/SubsetOTF/JP/NotoSansJP-Black.otf" },
    @{ Name='NotoSansKR-Black.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/SubsetOTF/KR/NotoSansKR-Black.otf" },
    @{ Name='DelaGothicOne-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/delagothicone/DelaGothicOne-Regular.ttf" },
    @{ Name='Pretendard-ExtraBold.otf'; Url="https://raw.githubusercontent.com/orioncactus/pretendard/$Pretendard/packages/pretendard/dist/public/static/Pretendard-ExtraBold.otf" }
)
foreach ($Asset in $Assets) {
    $Target = Join-Path $Destination $Asset.Name
    $Expected = if ($null -ne $Index) {
        $Index.fonts.PSObject.Properties.Value | Where-Object { $_.file -eq $Asset.Name } | Select-Object -First 1
    } else { $null }
    if ($Force -or !(Test-Path -LiteralPath $Target)) {
        Invoke-WebRequest -Uri $Asset.Url -OutFile ($Target + '.partial')
        if ($null -ne $Expected -and (Get-FileHash -LiteralPath ($Target + '.partial')).Hash.ToLower() -ne $Expected.sha256) {
            throw "Downloaded font checksum mismatch: $($Asset.Name)"
        }
        Move-Item -LiteralPath ($Target + '.partial') -Destination $Target -Force
    }
    if ($null -ne $Expected -and (Get-FileHash -LiteralPath $Target).Hash.ToLower() -ne $Expected.sha256) {
        throw "Bundled font checksum mismatch: $($Asset.Name)"
    }
    [pscustomobject]@{Name=$Asset.Name; Bytes=(Get-Item -LiteralPath $Target).Length; SHA256=(Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLower()}
}
$Notices = @(
    @{ Name='NotoSansCJK-OFL.txt'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/LICENSE" },
    @{ Name='DelaGothicOne-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/delagothicone/OFL.txt" },
    @{ Name='Pretendard-OFL.txt'; Url="https://raw.githubusercontent.com/orioncactus/pretendard/$Pretendard/LICENSE" }
)
foreach ($Notice in $Notices) {
    $Target = Join-Path $Licenses $Notice.Name
    if ($Force -or !(Test-Path -LiteralPath $Target)) { Invoke-WebRequest -Uri $Notice.Url -OutFile $Target }
}
