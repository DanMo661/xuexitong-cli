import QtQuick
import QtQuick.Shapes
import "." as Ui

// 品牌印章：花形 scalloped seal（FLstyle 形状语言——徽章/图标井用
// 花形不用正圆）+ 白色学仕帽 glyph。替代"学"字占位。
//
// 瓣数按尺寸给：金样 46px 徽章=四叶、136px hero≈10 瓣——小尺寸少瓣
// 才不糊；≥40px 用 8 瓣，更小退 6 瓣（内腔保持圆形好放 glyph）。
// path 用归一化坐标乘宽高生成，窗口尺寸无关。
Item {
    id: root

    property color base: Ui.Theme.primary
    property int petals: width >= 40 ? 8 : 6
    property real bulge: 1.16        // 外鼓控制点半径 = 内基圆 × bulge
    property color glyphColor: "#FFFFFF"
    readonly property real innerR: 0.5 / bulge   // 收基圆：外鼓后仍贴边界

    // 归一化花瓣路径：n 点圆周 + 每段 Q 曲线（控制点在外鼓半径上）
    readonly property string pathD: {
        const n = root.petals
        const r = root.innerR * 0.92
        let d = ""
        for (let i = 0; i < n; i++) {
            const a0 = (2 * Math.PI * i) / n - Math.PI / 2
            const a1 = (2 * Math.PI * (i + 1)) / n - Math.PI / 2
            const am = (a0 + a1) / 2
            const R = r * root.bulge
            const p0x = (0.5 + r * Math.cos(a0)) * width
            const p0y = (0.5 + r * Math.sin(a0)) * height
            const p1x = (0.5 + r * Math.cos(a1)) * width
            const p1y = (0.5 + r * Math.sin(a1)) * height
            const cx = (0.5 + R * Math.cos(am)) * width
            const cy = (0.5 + R * Math.sin(am)) * height
            d += (i === 0 ? `M ${p0x.toFixed(2)} ${p0y.toFixed(2)}` : "")
               + ` Q ${cx.toFixed(2)} ${cy.toFixed(2)} ${p1x.toFixed(2)} ${p1y.toFixed(2)}`
        }
        return d + " Z"
    }

    Shape {
        anchors.fill: parent
        antialiasing: true
        preferredRendererType: Shape.GeometryRenderer
        ShapePath {
            fillColor: root.base
            strokeColor: "transparent"
            strokeWidth: 0
            PathSvg { path: root.pathD }
        }
    }

    Glyphs {
        anchors.centerIn: parent
        width: Math.round(root.width * 0.56)
        height: Math.round(root.height * 0.56)
        thickness: Math.max(1.6, root.width * 0.10)
        kind: 9   // 学仕帽
        color: root.glyphColor
    }
}
