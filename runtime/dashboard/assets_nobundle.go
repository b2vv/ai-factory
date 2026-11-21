//go:build nobundle

package main

import (
	"embed"
	"io/fs"
	"testing/fstest"
)

// Test-only build (-tags nobundle) for a clean checkout without node_modules or ui/dist:
// the real HTML and CSS are embedded; app.js is a fixed stub. The bundle's own content is
// checked only in the default build.
//
//go:embed ui/index.html ui/style.css
var embedded embed.FS

const bundled = false

const stubBundle = "/* nobundle test stub: build ui/dist/app.js for the real bundle */\n"

var assets fs.FS = func() fs.FS {
	m := fstest.MapFS{"ui/dist/app.js": {Data: []byte(stubBundle)}}
	for _, name := range []string{"ui/index.html", "ui/style.css"} {
		data, err := fs.ReadFile(embedded, name)
		if err != nil {
			panic(err)
		}
		m[name] = &fstest.MapFile{Data: data}
	}
	return m
}()
