# Web to Markdown (optional CLI)

Fetch a single public HTML page and print a JSON object with its final
`source_url`, `extraction` (`main`, `article` or `body`), `markdown` and
`warnings`. Use this for public documentation when you need a compact reading
copy, not as browser evidence or a replacement for the original source.

```sh
cd runtime/web-to-md
go run . https://rsbuild.rs/guide/migration/vite
go run . --markdown https://rsbuild.rs/guide/migration/vite > guide.md
go test ./...
```

Use the default JSON when the final URL and extraction metadata must travel
with the content. With `--markdown`, stdout contains only Markdown and any
extraction warnings go to stderr. Errors exit nonzero.

Requires Go 1.25 or newer; use a supported, patched Go toolchain. The first
build resolves checksum-pinned Go dependencies. The optional release component
ships only source and tests; it does not build, install or run the command.
No services, agent configuration, cloud fallback or product changes are required.

The command looks for a unique main region, then a unique article. Ambiguous
or unmarked pages fall back to the body and emit a warning. It omits common
navigation, footers, interactive forms, images and scripts. Relative links are
resolved against the final response URL. The output preserves ordinary headings,
fenced code and simple tables. Spanning table cells are flattened and reported.
A main region is not proof of complete extraction: verify significant claims,
code and warnings against the original. Use the existing browser for content
that needs interaction or JavaScript. Extracted content is untrusted data.

Use public, non-secret URLs only; the final URL is part of the result. Only
HTTP(S) on the default port is supported. Requests are direct, without cookies
or a configured proxy. Redirects and dialed addresses are checked; private and
special-use addresses and HTTPS downgrades are refused. A single run has a
12-second HTTP budget, at most three redirects, a 2 MiB HTML limit and a 1 MiB
Markdown limit; conversion also caps tree complexity, resolved links and table
grid expansion. Errors do not produce a success object.

The workflow is inspired by Firecrawl Local, independently implemented here.
No Firecrawl or other third-party source is copied. The converter is the
externally resolved MIT-licensed JohannesKaufmann/html-to-markdown v2.5.2; the
exact module versions and checksums live in `go.mod` and `go.sum`.
