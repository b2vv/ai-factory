package capture

import "regexp"

// SanitizerVersion is part of the import contract. Changing rules can change payloads
// under an existing identity; importers must report conflicts, never silently overwrite.
const SanitizerVersion = "known-credentials-v1"
const RedactedText = "[REDACTED: possible credential content]"

// Match known credential indicators, then withhold the ENTIRE text. This deliberately
// favors false positives over guessing the end of nested/escaped/multiline secrets.
// It is not a general secret detector: unlabelled passwords and unknown encodings may
// remain. Only approved, source-validated exports may be submitted for real capture.
var credentialIndicators = []*regexp.Regexp{
	regexp.MustCompile(`(?i)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----`),
	regexp.MustCompile(`(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie)\b["'\s]*[:=]`),
	regexp.MustCompile(`(?i)\b(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|secret|secrets|token|credentials|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|session[_-]?token|aws_secret_access_key|aws_session_token)\b["'\s]*[:=]`),
	regexp.MustCompile(`(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{8,}`),
	regexp.MustCompile(`(?i)\b[a-z][a-z0-9+.-]*://[^\s/]+@`),
	regexp.MustCompile(`\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b`),
	regexp.MustCompile(`\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b`),
}

func SanitizeText(text string) (string, bool) {
	for _, re := range credentialIndicators {
		if re.MatchString(text) {
			return RedactedText, true
		}
	}
	return text, false
}
