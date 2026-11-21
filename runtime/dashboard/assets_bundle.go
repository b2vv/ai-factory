//go:build !nobundle

package main

import (
	"embed"
	"io/fs"
)

// The shipped binary embeds the built browser bundle (npm ci && npm run build → ui/dist/app.js).
//
//go:embed ui/index.html ui/style.css ui/dist/app.js
var embedded embed.FS

var assets fs.FS = embedded

const bundled = true
