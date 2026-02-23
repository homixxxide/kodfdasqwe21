import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

ApplicationWindow {
    id: root
    width: 1320
    height: 840
    visible: true
    title: "MetaMind v6.5"
    color: "#000000"

    flags: Qt.FramelessWindowHint | Qt.Window

    property bool splashDone: false
    property int currentPage: 0

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#180204" }
            GradientStop { position: 0.35; color: "#0b0b0d" }
            GradientStop { position: 0.7; color: "#090909" }
            GradientStop { position: 1.0; color: "#000000" }
        }
    }

    Rectangle {
        id: animatedGlow
        width: root.width * 1.1
        height: root.height * 1.1
        radius: width / 2
        anchors.centerIn: parent
        color: "#66ff0000"
        opacity: 0.22
        layer.enabled: true
        layer.effect: FastBlur { radius: 160 }

        SequentialAnimation on rotation {
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 360; duration: 30000; easing.type: Easing.InOutSine }
        }
    }

    Rectangle {
        id: chrome
        anchors.fill: parent
        anchors.margins: 14
        radius: 26
        color: "#0d0d0f"
        border.color: "#33ffffff"

        layer.enabled: true
        layer.effect: DropShadow {
            horizontalOffset: 0
            verticalOffset: 16
            radius: 32
            samples: 50
            color: "#88000000"
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                radius: 18
                color: "#1a1113"
                border.color: "#44ff6b6b"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    Label {
                        text: "METAMIND"
                        color: "#ffffff"
                        font.pixelSize: 28
                        font.bold: true
                        font.letterSpacing: 2.5
                    }

                    Label {
                        text: "v6.5"
                        color: "#ff4d4d"
                        font.pixelSize: 18
                        font.bold: true
                    }

                    Item { Layout.fillWidth: true }

                    Label {
                        text: metaBridge.statusText
                        color: "#d3d6db"
                        font.pixelSize: 13
                    }

                    Rectangle {
                        width: 40; height: 40; radius: 12
                        color: "#2f1518"
                        border.color: "#66ff6b6b"
                        Text {
                            anchors.centerIn: parent
                            text: "✕"
                            color: "white"
                            font.pixelSize: 18
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: Qt.quit()
                            onEntered: parent.color = "#5d121a"
                            onExited: parent.color = "#2f1518"
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 16

                Rectangle {
                    Layout.preferredWidth: 280
                    Layout.fillHeight: true
                    radius: 22
                    color: "#18181c"
                    border.color: "#2cffffff"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 14

                        Repeater {
                            model: ["Контрпики", "Мета", "Аналитика", "Скан"]
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 62
                                radius: 16
                                property bool active: index === root.currentPage
                                color: active ? "#b22222" : "#1f1f24"
                                border.color: active ? "#f07f7f" : "#29ffffff"

                                Behavior on color { ColorAnimation { duration: 220 } }
                                Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData
                                    color: "white"
                                    font.pixelSize: 16
                                    font.bold: true
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: {
                                        root.currentPage = index
                                        metaBridge.sendToast("Открыт раздел: " + modelData)
                                    }
                                    onEntered: parent.scale = 1.02
                                    onExited: parent.scale = 1.0
                                }
                            }
                        }

                        Item { Layout.fillHeight: true }

                        Label {
                            text: "Premium UI / QML"
                            color: "#96a0aa"
                            font.pixelSize: 12
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 22
                    color: "#17171a"
                    border.color: "#2affffff"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        Label {
                            text: "Главная панель"
                            color: "#ffffff"
                            font.pixelSize: 30
                            font.bold: true
                        }

                        Label {
                            text: "Техническая логика не меняется — обновлен только визуальный слой (QML)."
                            color: "#c7cbd2"
                            wrapMode: Text.WordWrap
                            font.pixelSize: 15
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            spacing: 12

                            Button {
                                text: "Автоскан"
                                onClicked: metaBridge.requestAutoScan()
                                background: Rectangle {
                                    radius: 14
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: "#ff4a4a" }
                                        GradientStop { position: 1.0; color: "#9e1d1d" }
                                    }
                                    border.color: "#ff9a9a"
                                }
                            }

                            Button {
                                text: "Обновить мету"
                                onClicked: metaBridge.requestMetaRefresh()
                                background: Rectangle {
                                    radius: 14
                                    color: "#22262f"
                                    border.color: "#48d5ff"
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 20
                            color: "#121317"
                            border.color: "#2effffff"

                            Canvas {
                                id: grid
                                anchors.fill: parent
                                onPaint: {
                                    var ctx = getContext("2d")
                                    ctx.clearRect(0, 0, width, height)
                                    ctx.strokeStyle = "rgba(255, 70, 70, 0.12)"
                                    ctx.lineWidth = 1
                                    for (var x = 0; x < width; x += 28) {
                                        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
                                    }
                                    for (var y = 0; y < height; y += 28) {
                                        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: islandToast
        width: Math.min(root.width * 0.45, 560)
        height: 54
        radius: 26
        anchors.horizontalCenter: parent.horizontalCenter
        y: 16
        color: "#ee15171d"
        border.color: "#54ffffff"
        opacity: 0.0

        Label {
            id: toastText
            anchors.centerIn: parent
            text: ""
            color: "#ffffff"
            font.pixelSize: 14
            font.bold: true
        }

        SequentialAnimation {
            id: toastAnim
            running: false
            NumberAnimation { target: islandToast; property: "opacity"; from: 0; to: 1; duration: 180 }
            PauseAnimation { duration: 1200 }
            NumberAnimation { target: islandToast; property: "opacity"; from: 1; to: 0; duration: 260 }
        }

        Connections {
            target: metaBridge
            function onToastRequested(message) {
                toastText.text = message
                toastAnim.restart()
            }
        }
    }

    Rectangle {
        id: splash
        anchors.fill: parent
        visible: !root.splashDone
        color: "#000000"
        opacity: visible ? 1 : 0

        Column {
            anchors.centerIn: parent
            spacing: 18

            Label {
                text: "Привет"
                color: "white"
                font.pixelSize: 62
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Label {
                text: "MetaMind"
                color: "#ff4d4d"
                font.pixelSize: 42
                font.bold: true
                anchors.horizontalCenter: parent.horizontalCenter
            }

            BusyIndicator {
                running: true
                width: 64
                height: 64
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }

        Timer {
            interval: 2400
            running: true
            repeat: false
            onTriggered: splashFade.start()
        }

        NumberAnimation {
            id: splashFade
            target: splash
            property: "opacity"
            from: 1
            to: 0
            duration: 700
            easing.type: Easing.InOutCubic
            onFinished: root.splashDone = true
        }
    }
}
