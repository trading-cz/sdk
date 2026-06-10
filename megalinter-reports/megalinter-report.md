## ✅⚠️[MegaLinter](https://megalinter.io/9.5.0) analysis: Success with warnings



| Descriptor  |                                               Linter                                                |Files|Fixed|Errors|Warnings|Elapsed time|
|-------------|-----------------------------------------------------------------------------------------------------|----:|----:|-----:|-------:|-----------:|
|✅ ACTION    |[actionlint](https://megalinter.io/9.5.0/descriptors/action_actionlint)                              |    4|     |     0|       0|        0.0s|
|⚠️ MARKDOWN  |[markdownlint](https://megalinter.io/9.5.0/descriptors/markdown_markdownlint)                        |    3|    0|     9|       0|       0.79s|
|✅ MARKDOWN  |[markdown-table-formatter](https://megalinter.io/9.5.0/descriptors/markdown_markdown_table_formatter)|    3|    2|     0|       0|       0.26s|
|✅ PYTHON    |[black](https://megalinter.io/9.5.0/descriptors/python_black)                                        |   90|   41|     0|       0|       3.67s|
|✅ PYTHON    |[isort](https://megalinter.io/9.5.0/descriptors/python_isort)                                        |   90|   50|     0|       0|       0.32s|
|✅ PYTHON    |[mypy](https://megalinter.io/9.5.0/descriptors/python_mypy)                                          |   72|     |     0|       0|       2.94s|
|✅ PYTHON    |[pylint](https://megalinter.io/9.5.0/descriptors/python_pylint)                                      |   73|     |     0|       0|       7.26s|
|✅ PYTHON    |[ruff](https://megalinter.io/9.5.0/descriptors/python_ruff)                                          |   90|   50|     0|       0|       0.06s|
|✅ REPOSITORY|[gitleaks](https://megalinter.io/9.5.0/descriptors/repository_gitleaks)                              |  yes|     |    no|      no|       0.55s|
|✅ REPOSITORY|[trivy](https://megalinter.io/9.5.0/descriptors/repository_trivy)                                    |  yes|     |    no|      no|      10.64s|
|✅ SPELL     |[lychee](https://megalinter.io/9.5.0/descriptors/spell_lychee)                                       |    8|     |     0|       0|       0.27s|
|✅ YAML      |[prettier](https://megalinter.io/9.5.0/descriptors/yaml_prettier)                                    |    5|    0|     0|       0|       0.56s|
|✅ YAML      |[yamllint](https://megalinter.io/9.5.0/descriptors/yaml_yamllint)                                    |    5|     |     0|       0|       0.43s|

## Detailed Issues

<details>
<summary>⚠️ MARKDOWN / markdownlint - 9 errors</summary>

```
docs/ARCHITECTURE.md:8 error MD040/fenced-code-language Fenced code blocks should have a language specified [Context: "```"]
docs/ARCHITECTURE.md:113 error MD040/fenced-code-language Fenced code blocks should have a language specified [Context: "```"]
docs/ARCHITECTURE.md:132 error MD040/fenced-code-language Fenced code blocks should have a language specified [Context: "```"]
docs/ARCHITECTURE.md:150:5 error MD060/table-column-style Table column style [Table pipe is missing space to the left for style "compact"]
docs/ARCHITECTURE.md:150:9 error MD060/table-column-style Table column style [Table pipe is missing space to the left for style "compact"]
docs/ARCHITECTURE.md:150:13 error MD060/table-column-style Table column style [Table pipe is missing space to the left for style "compact"]
docs/ARCHITECTURE.md:150:1 error MD060/table-column-style Table column style [Table pipe is missing space to the right for style "compact"]
docs/ARCHITECTURE.md:150:5 error MD060/table-column-style Table column style [Table pipe is missing space to the right for style "compact"]
docs/ARCHITECTURE.md:150:9 error MD060/table-column-style Table column style [Table pipe is missing space to the right for style "compact"]
```

</details>

See detailed reports in MegaLinter artifacts

[![MegaLinter is graciously provided by OX Security](https://raw.githubusercontent.com/oxsecurity/megalinter/main/docs/assets/images/ox-banner.png)](https://www.ox.security/?ref=megalinter)
Show us your support by [**starring ⭐ the repository**](https://github.com/oxsecurity/megalinter)