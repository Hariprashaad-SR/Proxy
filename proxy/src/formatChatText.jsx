// Chat text comes from Groq / bot_manager as plain text with light markdown
// (**bold**, blank-line-separated paragraphs) — browsers don't render that
// on their own, so turn it into actual line breaks and <strong> instead of
// showing literal asterisks.
export default function formatChatText(text) {
  return text.split("\n").map((line, i) => (
    <div key={i}>
      {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
        part.startsWith("**") && part.endsWith("**") ? <strong key={j}>{part.slice(2, -2)}</strong> : part
      )}
    </div>
  ));
}
