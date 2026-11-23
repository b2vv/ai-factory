package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/JohannesKaufmann/html-to-markdown/v2/converter"
	"github.com/JohannesKaufmann/html-to-markdown/v2/plugin/base"
	"github.com/JohannesKaufmann/html-to-markdown/v2/plugin/commonmark"
	"github.com/JohannesKaufmann/html-to-markdown/v2/plugin/table"
	"golang.org/x/net/html"
)

type result struct {
	Source     string   `json:"source_url"`
	Extraction string   `json:"extraction"`
	Markdown   string   `json:"markdown"`
	Warnings   []string `json:"warnings"`
}

func convert(input io.Reader, source *url.URL) (result, error) {
	raw, err := readLimit(input, maxDecoded, "decoded HTML exceeds 6 MiB limit")
	if err != nil {
		return result{}, err
	}
	doc, err := html.Parse(bytes.NewReader(raw))
	if err != nil {
		return result{}, err
	}
	out := result{Source: source.String(), Warnings: []string{}}
	warn := func(name string) {
		if !slices.Contains(out.Warnings, name) {
			out.Warnings = append(out.Warnings, name)
		}
	}
	var body *html.Node
	var mains, articles []*html.Node
	nodes := 0
	var visit func(*html.Node, int, bool, bool) error
	visit = func(n *html.Node, depth int, inMain, inArticle bool) error {
		nodes++
		if nodes > 50000 || depth > 128 {
			return errors.New("HTML tree exceeds complexity limit")
		}
		if n.Type == html.ElementNode {
			if n.Data == "body" {
				body = n
			}
			isMain := mainRegion(n)
			if isMain && !inMain {
				mains = append(mains, n)
			}
			if n.Data == "article" && !inArticle {
				articles = append(articles, n)
			}
			inMain, inArticle = inMain || isMain, inArticle || n.Data == "article"
		}
		for child := n.FirstChild; child != nil; {
			next := child.NextSibling
			if child.Type == html.CommentNode || child.Type == html.ElementNode && (remove(child.Data) ||
				child.Data == "header" && !inMain && !inArticle && !containsRegion(child)) {
				n.RemoveChild(child)
			} else if child.Type == html.ElementNode && child.Data == "img" {
				if alt := altText(child); alt != "" {
					n.InsertBefore(&html.Node{Type: html.TextNode, Data: alt}, child)
				}
				n.RemoveChild(child)
			} else if err := visit(child, depth+1, inMain, inArticle); err != nil {
				return err
			}
			child = next
		}
		return nil
	}
	if err := visit(doc, 0, false, false); err != nil {
		return result{}, err
	}
	root := body
	out.Extraction = "body"
	switch {
	case len(mains) == 1:
		root, out.Extraction = mains[0], "main"
	case len(mains) > 1:
		warn("multiple_main_regions")
	case len(articles) == 1:
		root, out.Extraction = articles[0], "article"
	default:
		warn("main_not_identified")
	}
	if root == nil {
		return result{}, errors.New("HTML body missing")
	}

	// Rewrite links using the actual final URL; never trust the document's base tag.
	linkBytes, tableCells := 0, 0
	var prepare func(*html.Node) error
	prepare = func(n *html.Node) error {
		if n.Type == html.ElementNode {
			if n.Data == "table" {
				tableCells += tableGridSize(n)
				if tableCells > 16000 {
					return errors.New("table grid exceeds conversion limit")
				}
			}
			attrs := n.Attr[:0]
			for _, a := range n.Attr {
				switch a.Key {
				case "role":
					if a.Val == "tablist" || a.Val == "tabpanel" {
						warn("interactive_tabs_present")
					}
				case "href":
					if n.Data != "a" {
						continue
					}
					target, err := url.Parse(strings.TrimSpace(a.Val))
					if err != nil {
						continue
					}
					target = source.ResolveReference(target)
					if target.User != nil || target.Host == "" || (target.Scheme != "https" && target.Scheme != "http") {
						continue
					}
					a.Val = target.String()
					linkBytes += len(a.Val)
					if linkBytes > 256<<10 {
						return errors.New("resolved links exceed conversion limit")
					}
				case "rowspan", "colspan":
					if a.Val != "1" {
						warn("complex_table_flattened")
					}
					continue
				}
				attrs = append(attrs, a)
			}
			n.Attr = attrs
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			if err := prepare(c); err != nil {
				return err
			}
		}
		return nil
	}
	if err := prepare(root); err != nil {
		return result{}, err
	}

	c := converter.NewConverter(converter.WithPlugins(
		base.NewBasePlugin(), commonmark.NewCommonmarkPlugin(),
		table.NewTablePlugin(table.WithCellPaddingBehavior(table.CellPaddingBehaviorMinimal),
			table.WithNewlineBehavior(table.NewlineBehaviorPreserve)),
	))
	markdown, err := c.ConvertNode(root)
	if err != nil {
		return result{}, err
	}
	out.Markdown = strings.TrimSpace(string(markdown))
	if out.Markdown == "" {
		return result{}, errors.New("no static content extracted; try the browser")
	}
	if len(out.Markdown) > 1<<20 {
		return result{}, errors.New("Markdown exceeds 1 MiB limit")
	}
	return out, nil
}

// Count the rectangular grid the converter can create, not just populated cells.
// Span attributes are removed before conversion, and nested tables are counted separately.
func tableGridSize(root *html.Node) int {
	rows, width := 0, 0
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n != root && n.Type == html.ElementNode && n.Data == "table" {
			return
		}
		if n.Type == html.ElementNode && n.Data == "tr" {
			rows++
			cells := 0
			for c := n.FirstChild; c != nil; c = c.NextSibling {
				if c.Type == html.ElementNode && (c.Data == "td" || c.Data == "th") {
					cells++
				}
			}
			width = max(width, cells)
			return
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}
	walk(root)
	return rows * width
}

// mainRegion reports a <main> element or a role attribute whose token list names main, in any case.
func mainRegion(n *html.Node) bool {
	if n.Data == "main" {
		return true
	}
	for _, a := range n.Attr {
		if a.Key == "role" && slices.ContainsFunc(strings.Fields(a.Val), func(v string) bool { return strings.EqualFold(v, "main") }) {
			return true
		}
	}
	return false
}

// containsRegion reports whether a main or article region lies inside n (a header wrapping the content is kept).
func containsRegion(n *html.Node) bool {
	for c := n.FirstChild; c != nil; c = c.NextSibling {
		if c.Type == html.ElementNode && (c.Data == "article" || mainRegion(c) || containsRegion(c)) {
			return true
		}
	}
	return false
}

// altText is an image's alt text as plain text: whitespace collapsed, at most 200 bytes on a rune boundary.
func altText(n *html.Node) string {
	for _, a := range n.Attr {
		if a.Key == "alt" {
			alt := strings.Join(strings.Fields(a.Val), " ")
			for len(alt) > 200 {
				_, size := utf8.DecodeLastRuneInString(alt)
				alt = alt[:len(alt)-size]
			}
			return alt
		}
	}
	return ""
}

// remove drops non-content elements. Forms stay (their content is often the page); only controls go.
func remove(tag string) bool {
	switch tag {
	case "script", "style", "nav", "footer", "input", "select", "textarea", "button", "datalist", "iframe", "svg", "picture", "video", "audio", "template", "noscript":
		return true
	}
	return false
}

func run(args []string, stdout, stderr io.Writer, load func(context.Context, string) (result, error)) int {
	markdownOnly := len(args) == 2 && args[0] == "--markdown"
	if markdownOnly {
		args = args[1:]
	}
	if len(args) != 1 || strings.HasPrefix(args[0], "-") {
		fmt.Fprintln(stderr, "usage: web-to-md [--markdown] <public-http(s)-url>")
		return 2
	}
	r, err := load(context.Background(), args[0])
	if err == nil {
		if markdownOnly {
			for _, warning := range r.Warnings {
				fmt.Fprintf(stderr, "warning: %s\n", warning)
			}
			_, err = fmt.Fprintln(stdout, r.Markdown)
		} else {
			err = json.NewEncoder(stdout).Encode(r)
		}
	}
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr, fetch))
}
