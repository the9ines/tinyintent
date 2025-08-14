// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "TinyIntent",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "tinyintent", targets: ["TinyIntentMain"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "TinyIntentMain",
            dependencies: []
        )
    ]
)