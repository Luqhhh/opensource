# reusable html

Historical upstream example: https://github.com/lepture/mistune/blob/6470c42b2087a4649ad0437227cf7b5c570c3a91/README.rst#L70-L73

Reuse the callable named markdown to render Markdown to an HTML string. Preserve the old default behavior: raw HTML is retained and ordinary newlines remain soft. The original expression is silent in a script. External checks cover empty text, emphasis, Unicode, raw HTML, and repeated calls.

```python
import mistune

markdown = mistune.Markdown()
markdown('I am using **mistune markdown parser**')
```
