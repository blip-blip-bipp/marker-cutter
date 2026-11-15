// Renders the Marker Cutter app icon straight from the logo's vector geometry, so every size is crisp.
//
//   swiftc -O packaging/make_icons.swift -o /tmp/make_icons && /tmp/make_icons packaging/icons
//
// Outputs into the given folder:
//   AppIcon.iconset/*.png   macOS iconset (run `iconutil -c icns AppIcon.iconset` for the .icns)
//   AppIcon-1024.png        master image (macOS style, transparent margin)
//   win/icon_<n>.png        Windows sizes (fuller tile, little margin); packaging/make_ico.py joins them into AppIcon.ico
//
// Logo = the SVG in the app header: viewBox 24, stroke 2, round caps, path "M4 12h2M8 7v10M12 4v16M16 8v8M20 11v2".
import AppKit
import ImageIO
import UniformTypeIdentifiers

let outDir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icons"
let fm = FileManager.default

// logo segments in SVG units (y down)
let segments: [((Double, Double), (Double, Double))] = [
    ((4, 12), (6, 12)), ((8, 7), (8, 17)), ((12, 4), (12, 20)), ((16, 8), (16, 16)), ((20, 11), (20, 13)),
]

func rgb(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: a)
}

/// Apple-style "squircle": |x|^n + |y|^n = 1 (n=5 is close to the macOS icon shape)
func squircle(in r: CGRect, n: Double = 5) -> CGPath {
    let p = CGMutablePath(), steps = 360
    for i in 0...steps {
        let t = Double(i) / Double(steps) * 2 * .pi
        let c = cos(t), s = sin(t)
        let x = (c < 0 ? -1.0 : 1.0) * pow(abs(c), 2 / n), y = (s < 0 ? -1.0 : 1.0) * pow(abs(s), 2 / n)
        let pt = CGPoint(x: r.midX + CGFloat(x) * r.width / 2, y: r.midY + CGFloat(y) * r.height / 2)
        i == 0 ? p.move(to: pt) : p.addLine(to: pt)
    }
    p.closeSubpath()
    return p
}

func render(size: Int, windows: Bool) -> CGImage {
    let S = CGFloat(size)
    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let ctx = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.setAllowsAntialiasing(true); ctx.setShouldAntialias(true); ctx.interpolationQuality = .high

    // tile: macOS leaves Apple's transparent margin; Windows (and the tiny macOS sizes) fill more of the canvas
    let tight = windows || size <= 32
    let inset = S * (tight ? 0.04 : 100.0 / 1024.0)
    let body = CGRect(x: inset, y: inset, width: S - 2 * inset, height: S - 2 * inset)
    let shape = squircle(in: body)

    // drop shadow under the tile (large sizes only, it just muddies tiny icons)
    if size >= 128 {
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -S * 0.012), blur: S * 0.025, color: rgb(0x000000, 0.35))
        ctx.addPath(shape); ctx.setFillColor(rgb(0x1A1A1A)); ctx.fillPath()
        ctx.restoreGState()
    }

    // tile fill: Tracks Live toolbar grey fading to its darker window colour
    ctx.saveGState()
    ctx.addPath(shape); ctx.clip()
    let bg = CGGradient(colorsSpace: cs, colors: [rgb(0x30333B), rgb(0x1A1A1C)] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(bg, start: CGPoint(x: S / 2, y: body.maxY), end: CGPoint(x: S / 2, y: body.minY), options: [])
    ctx.restoreGState()

    // hairline highlight on the tile edge
    if size >= 64 {
        ctx.addPath(shape); ctx.setStrokeColor(rgb(0xFFFFFF, 0.10)); ctx.setLineWidth(max(1, S * 0.004)); ctx.strokePath()
    }

    // waveform: logo bars, round caps, blue gradient with a soft glow
    let frac: CGFloat = size <= 16 ? 0.82 : (size <= 48 ? 0.66 : (windows ? 0.58 : 0.55))   // bigger glyph where pixels are scarce
    let strokeUnits: CGFloat = size <= 16 ? 1.5 : 2                            // slimmer bars at 16px so the gaps between them stay open
    let unit = frac * body.width / 18                                          // glyph spans 18 SVG units (3...21)
    func pt(_ x: Double, _ y: Double) -> CGPoint {
        CGPoint(x: body.midX + CGFloat(x - 12) * unit, y: body.midY - CGFloat(y - 12) * unit)
    }
    let bars = CGMutablePath()
    for (a, b) in segments { bars.move(to: pt(a.0, a.1)); bars.addLine(to: pt(b.0, b.1)) }
    let stroked = bars.copy(strokingWithWidth: strokeUnits * unit, lineCap: .round, lineJoin: .round, miterLimit: 10)

    if size >= 64 {
        ctx.saveGState()
        ctx.setShadow(offset: .zero, blur: S * 0.035, color: rgb(0x1694ED, 0.55))
        ctx.addPath(stroked); ctx.setFillColor(rgb(0x1694ED)); ctx.fillPath()
        ctx.restoreGState()
    }
    ctx.saveGState()
    ctx.addPath(stroked); ctx.clip()
    let blue = CGGradient(colorsSpace: cs, colors: [rgb(0x45B4FF), rgb(0x0B86E0)] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(blue, start: pt(12, 4), end: pt(12, 20), options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
    ctx.restoreGState()

    return ctx.makeImage()!
}

func writePNG(_ img: CGImage, to path: String) {
    let url = URL(fileURLWithPath: path) as CFURL
    guard let dest = CGImageDestinationCreateWithURL(url, UTType.png.identifier as CFString, 1, nil) else { fatalError("can't write \(path)") }
    CGImageDestinationAddImage(dest, img, nil)
    guard CGImageDestinationFinalize(dest) else { fatalError("failed writing \(path)") }
}

let iconset = "\(outDir)/AppIcon.iconset", win = "\(outDir)/win"
for d in [iconset, win] { try? fm.removeItem(atPath: d); try! fm.createDirectory(atPath: d, withIntermediateDirectories: true) }

// macOS iconset: name -> pixel size
let mac: [(String, Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32), ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256), ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
for (name, px) in mac { writePNG(render(size: px, windows: false), to: "\(iconset)/\(name).png") }
writePNG(render(size: 1024, windows: false), to: "\(outDir)/AppIcon-1024.png")
for px in [16, 24, 32, 48, 64, 128, 256] { writePNG(render(size: px, windows: true), to: "\(win)/icon_\(px).png") }
print("wrote \(mac.count) iconset PNGs, the 1024 master and 7 Windows sizes to \(outDir)")
