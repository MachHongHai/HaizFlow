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
    @{ Name='ArchivoBlack-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/archivoblack/ArchivoBlack-Regular.ttf" },
    @{ Name='Barlow-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/barlow/Barlow-Bold.ttf" },
    @{ Name='FiraSans-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/firasans/FiraSans-Bold.ttf" },
    @{ Name='SairaCondensed-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/sairacondensed/SairaCondensed-Bold.ttf" },
    @{ Name='ChakraPetch-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/chakrapetch/ChakraPetch-Bold.ttf" },
    @{ Name='Kanit-SemiBold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/kanit/Kanit-SemiBold.ttf" },
    @{ Name='Sarabun-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/sarabun/Sarabun-Bold.ttf" },
    @{ Name='Bungee-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/bungee/Bungee-Regular.ttf" },
    @{ Name='Pacifico-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/pacifico/Pacifico-Regular.ttf" },
    @{ Name='PatrickHand-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/patrickhand/PatrickHand-Regular.ttf" },
    @{ Name='AmaticSC-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/amaticsc/AmaticSC-Bold.ttf" },
    @{ Name='Itim-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/itim/Itim-Regular.ttf" },
    @{ Name='NotoSerifSC-Bold.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Serif/SubsetOTF/SC/NotoSerifSC-Bold.otf" },
    @{ Name='NotoSerifTC-Bold.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Serif/SubsetOTF/TC/NotoSerifTC-Bold.otf" },
    @{ Name='NotoSerifJP-Bold.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Serif/SubsetOTF/JP/NotoSerifJP-Bold.otf" },
    @{ Name='NotoSerifKR-Bold.otf'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Serif/SubsetOTF/KR/NotoSerifKR-Bold.otf" },
    @{ Name='Maitree-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/maitree/Maitree-Bold.ttf" },
    @{ Name='Judson-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/judson/Judson-Bold.ttf" },
    @{ Name='BeVietnamPro-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/bevietnampro/BeVietnamPro-Bold.ttf" },
    @{ Name='Anton-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/anton/Anton-Regular.ttf" },
    @{ Name='BarlowCondensed-SemiBold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/barlowcondensed/BarlowCondensed-SemiBold.ttf" },
    @{ Name='Lato-Bold.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/lato/Lato-Bold.ttf" },
    @{ Name='Lobster-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/lobster/Lobster-Regular.ttf" },
    @{ Name='BreeSerif-Regular.ttf'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/breeserif/BreeSerif-Regular.ttf" },
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
    @{ Name='ArchivoBlack-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/archivoblack/OFL.txt" },
    @{ Name='Barlow-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/barlow/OFL.txt" },
    @{ Name='FiraSans-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/firasans/OFL.txt" },
    @{ Name='SairaCondensed-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/sairacondensed/OFL.txt" },
    @{ Name='ChakraPetch-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/chakrapetch/OFL.txt" },
    @{ Name='Kanit-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/kanit/OFL.txt" },
    @{ Name='Sarabun-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/sarabun/OFL.txt" },
    @{ Name='Bungee-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/bungee/OFL.txt" },
    @{ Name='Pacifico-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/pacifico/OFL.txt" },
    @{ Name='PatrickHand-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/patrickhand/OFL.txt" },
    @{ Name='AmaticSC-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/amaticsc/OFL.txt" },
    @{ Name='Itim-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/itim/OFL.txt" },
    @{ Name='NotoSerifCJK-OFL.txt'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Serif/LICENSE" },
    @{ Name='Maitree-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/maitree/OFL.txt" },
    @{ Name='Judson-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/judson/OFL.txt" },
    @{ Name='BeVietnamPro-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/bevietnampro/OFL.txt" },
    @{ Name='Anton-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/anton/OFL.txt" },
    @{ Name='BarlowCondensed-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/barlowcondensed/OFL.txt" },
    @{ Name='Lato-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/lato/OFL.txt" },
    @{ Name='Lobster-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/lobster/OFL.txt" },
    @{ Name='BreeSerif-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/breeserif/OFL.txt" },
    @{ Name='NotoSansCJK-OFL.txt'; Url="https://raw.githubusercontent.com/notofonts/noto-cjk/$Noto/Sans/LICENSE" },
    @{ Name='DelaGothicOne-OFL.txt'; Url="https://raw.githubusercontent.com/google/fonts/$Google/ofl/delagothicone/OFL.txt" },
    @{ Name='Pretendard-OFL.txt'; Url="https://raw.githubusercontent.com/orioncactus/pretendard/$Pretendard/LICENSE" }
)
foreach ($Notice in $Notices) {
    $Target = Join-Path $Licenses $Notice.Name
    if ($Force -or !(Test-Path -LiteralPath $Target)) { Invoke-WebRequest -Uri $Notice.Url -OutFile $Target }
}
