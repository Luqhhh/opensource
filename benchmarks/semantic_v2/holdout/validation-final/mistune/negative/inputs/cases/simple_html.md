# simple html

Historical upstream example: https://github.com/lepture/mistune/blob/6470c42b2087a4649ad0437227cf7b5c570c3a91/README.rst#L61-L64

Render the supplied Markdown as HTML using the documented convenience function. The expression is silent in a script. Checks cover empty input, plain text, emphasis, Unicode and escaping.

```python
import mistune

mistune.markdown('I am using **mistune markdown parser**')
# output: <p>I am using <strong>mistune markdown parser</strong></p>
```
