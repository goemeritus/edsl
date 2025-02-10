# Changelog

## [0.1.43] - TBD 
### Added
- (*In progress*) A universal remote cache is available for retrieving responses that have been previously run by any user (i.e., if you run a question that you or another user have run before, you will retrieve that response at no cost to you). It is available for all jobs run remotely by default, and new responses for any remote jobs are automatically added to it. If you want to draw fresh responses you can use `run(fresh_cache=True)` or `run(cache=Cache()`. If you want to draw responses from a different cache you can use `run(cache=<my_cache>)` (insert your own cache object). If you draw a fresh response for a question that has already been run, the new response is also added to the universal remote cache with an index (`n=2`, etc.). Universal remote cache is not available for jobs run locally. See the [remote cache](https://docs.expectedparrot.com/en/latest/remote_caching.html) section for more details.

- (*In progress*) You can now use your own keys from service providers to run jobs remotely and store them at the [Keys](https://www.expectedparrot.com/home/keys) page of your [Coop account](https://www.expectedparrot.com/login) (in lieu of your `.env` file). You can also grant access to other users (without sharing the keys directly), set limits on their usage and set RPM/TPM limits.

- (*In progress*) Parameter `run(background=True)` can be used to run a remote survey in the background so that you can continue working in your workspace. You will automatically get an email notification when the job is completed. You can check the status of the job at any time by attempting to return the results as usual, e.g., `results.columns`. 

- Method `ScenarioList.from_pdf_to_image(<filename>)` generates a scenario for each page of a pdf converted into a jpeg (to use as an image instead of converting to text). Companion method `Scenario.from_pdf_to_image(<filename>)` generates a key/value for each page within the same scenario object to allow you to use multiple images at the same time. See a [notebook of examples](https://www.expectedparrot.com/content/ea777fab-9cb1-4738-8fa3-bbdef20ed60d).

- Question types multiple choice and checkbox now (also) take an optional parameter `option_labels` consisting of descriptions for the (required) `question_options`. The option labels must be a list that includes a label for each option; in contrast, option labels for linear scale and matrix questions are an optional dictionary that uses the question options as the keys and any number of labels can be included (e.g., you could just have option labels for the first and last linear scale options, whereas if you provide any labels for a multiple choice or checkbox question the number of labels must equal the number of options). This can be useful if you want to keep answer multiple choice or checkbox options short but include more details for the model to reference. 

### Changed

### Fixed
- A bug preventing iterations on remote inference.


## [0.1.42] - 2025-01-24
### Added
- DeepSeek models, e.g., `Model("deepseek-reasoner")`.

- The name of the inference service is now included in the `Model` parameters and `Results` objects. This can be useful when the same model is provided by multiple services.

- The model pricing page at Coop shows daily test results for available models: https://www.expectedparrot.com/home/pricing. The same information can also be returned by calling the method `Model.check_working_models()`. Check the models for a particular service provider by passing the name of the service: `Model.check_working_models(service="google")`.

### Changed
- Default size limits on question texts have been removed.

### Fixed

## [0.1.41] - 2025-01-19
### Changed
- Modified default RPM to avoid timeout issues.


## [0.1.40] - 2025-01-15
### Added
- Question type `QuestionDict` returns a response as a dictionary with specified keys and (optionally) specified value types and descriptions. Details: https://docs.expectedparrot.com/en/latest/questions.html#questiodict-class

### Changed
- Results of jobs run remotely are no longer automatically synced to your local cache. Now, a new cache for results is automatically generated and attached to a results object; you can access it by calling `results.cache`. Results now also include the following fields for the associated cache: `cache_keys.<question_name>_cache_key` (the unique identifier for a cache entry) and `cache_used.<question_name>_cache_used` (an indicator whether the default cache was used to provide the response--this is either your local cache or remote cache, or a cache that was passed to the `run` method, if used instead of local or remote).

- Improvements to the web-based progress bar for remote jobs.

### Fixed
- Occasional timeout issue should be fixed by modifications to caching noted above.


## [0.1.39] - 2025-01-08
### Added
- Question type `QuestionMatrix`. Details: https://docs.expectedparrot.com/en/latest/questions.html#questionmatrix-class

- A `join()` method for objects. 

- `FileStore` method `create_link()` embeds a file in the HTML of a notebook and generates a download link for it. Examples: https://docs.expectedparrot.com/en/latest/filestore.html

### Changed
- Exceptions report is displayed as a clickable link.

- Improvements to table display of results returned by `select()` method.

- Improvements to status messages displayed in a table log when a job is running.

- `Model.available()` now uses Coop by default (all models available with remote inference are returned). If remote inference is not activated then only models available locally are returned (based on stored personal API keys).

### Fixed
- Progress bar shows total interviews instead of total unique interviews (iterations may be >1).


## [0.1.38] - 2024-11-26
### Added
- `Results` are now automatically displayed in a scrollable table when you call `select()` on them. You can also call `table().long()` to display results in a long-view table. This replaces the need to call `print(format="rich")`. See examples in the starter tutorial.

### Changed
- The progress bar is now web-based and a link to view it in a new tab is automatically returned when you call the `run()` method on a survey (`progress_bar=True` by default). See examples in the starter tutorial.

### Fixed
- Results were automatically appending cache; this was removed.


## [0.1.37] - 2024-11-14
### Added
- EDSL Authentication Token:  If you attempt to run a survey remotely without having stored your EXPECTED_PARROT_API_KEY, a message will appear providing a Coop login link. Clicking this link and logging in will automatically store your key in your *.env* file.

### Changed
- The `AgentList` method `from_csv()` now allows you to (optionally) automatically specify the `name` parameters for agents by including a column "name" in the CSV. Other columns are (still) passed as agent `traits`. See an example: https://docs.expectedparrot.com/en/latest/agents.html#from-a-csv-file

- The `Job` method `run()` now takes a parameter `remote_inference_results_visibility` to set the visibility of results of jobs that are being run remotely. The allowed visibility settings are `public`, `private` and `unlisted` (the default setting is unlisted). This parameter has the same effect as passing the parameter `visibility` to the `push()` and `patch()` methods for posting and updating objects at the Coop. For example, these commands have the same effect when remote inference activated:

```
Survey.example().run() 
```
```
Survey.example().run(remote_inference_visibility="unlisted")
```

### Fixed
- Bug in using f-strings and scenarios at once. Example usage: https://docs.expectedparrot.com/en/latest/scenarios.html#using-f-strings-with-scenarios

- Bug in optional question parameters `answering_instructions` and `question_presentation`, which can be used to modify user prompts separately from modifying question texts. Example usage: https://docs.expectedparrot.com/en/latest/questions.html#optional-question-parameters


## [0.1.36] - 2024-10-28
### Added
- Method `show_prompts()` can be called on a `Survey` to display the user prompt and system prompt. This is in addition to the existing method `prompts()` that is called on a `Job` which will return the prompts and additional information about the questions, agents, models and estimated costs. Learn more: https://docs.expectedparrot.com/en/latest/prompts.html

- Documentation on storing API keys as "secrets" for using EDSL in Colab.

### Changed
- `Conversation` module works with multiple models at once.

- Improved features for adding new models.


## [0.1.35] - 2024-10-17
### Fixed
- Access to Open AI o1 models


## [0.1.34] - 2024-10-15
### Added
- Survey Builder is a new interface for creating and launching hybrid human-AI surveys. It is fully integrated with EDSL and Coop. Get access by activating beta features from your Coop account profile page. Learn more: https://docs.expectedparrot.com/en/latest/survey_builder.html

- `Jobs` method `show_prompts()` returns a table showing the user and system prompts that will be used with a survey, together with information about the agent and model and estimated cost for each interview. `Jobs` method `prompts` returns the information in a dataset.

- `Scenario` objects can contain multiple images to be presented to a model at once (works with Google models).

### Fixed
- Bug in piping a `ScenarioList` containing multiple lists of `question_options` to use with questions.


## [0.1.33] - 2024-09-26
### Added 

- Optional parameters for `Question` objects:
    - `include_comment = False` prevents a `comment` field from being added to a question (default is `True`: all question types other than free text automatically include a field for the model to comment on its answer, unless this parameter is passed) 
    - `use_code = True` modifies user prompts for question types that take `question_options` to instruct the model to return the integer code for an option instead of the option value (default is `False`)
    - `answering_instructions` and `question_presentation` allow you to control exact prompt language and separate instructions for the presentation of a question
    - `permissive = True` turns off enforcement of question constraints (e.g., if min/max selections for a checkbox question have been specified, you can set `permissive = True` to allow responses that contain fewer or greater selections) (default is `False`)

- Methods for `Question` objects:
    - `loop()` generates a list of versions of a question for a `ScenarioList` that is passed to it. Questions are constructed with a `{{ placeholder }}` for a scenario as usual, but each scenario value is added to the question when it is created instead of when a survey is run (which is done with the `by()` method). Survey results for looped questions include fields for each unique question but no `scenario` field. See examples: https://docs.expectedparrot.com/en/latest/starter_tutorial.html#adding-scenarios-using-the-loop-method and https://docs.expectedparrot.com/en/latest/scenarios.html#looping 

- Methods for `ScenarioList` objects:
    - `unpivot()` expands a scenario list by specified identifiers
    - `pivot()` undoes `unpivot()`, collapsing scenarios by identifiers
    - `give_valid_names()` generates valid Pythonic identifiers for scenario keys
    - `group_by()` groups scenarios by identifiers or applies a function to the values of the specified variables
    - `from_wikipedia_table()` converts a Wikipedia table into a scenario list. See examples: https://docs.expectedparrot.com/en/latest/notebooks/scenario_list_wikipedia.html
    - `to_docx()` exports scenario lists as structured Docx documents

- Optional parameters for `Model` objects: 
    - `raise_validation_errors = False` causes exceptions to only be raised (interrupting survey execution) when a model returns nothing at all (default: `raise_validation_errors = True`)
    - `print_exceptions = False` causes exceptions to not be printed at all (default: `print_exceptions = True`)

- Columns in `Results` for monitoring token usage:
    - `generated_tokens` shows the tokens that were generated by the model
    - `raw_model_response.<question_name>_cost` shows the cost of the result for the question, applying the token quanities & prices
    - `raw_model_response.<question_name>_one_usd_buys` shows the number of results for the question that 1USD will buy
    - `raw_model_response.<question_name>_raw_model_response` shows the raw response for the question

- Methods for `Results` objects:
    - `tree()` displays a nested tree for specified components
    - `generate_html()` and `save_html()` generate and save HTML code for displaying results

### Changed
- General improvements to exceptions reports. 

- General improvements to the progress bar: `survey.run(progress_bar=True)`

- Question validation methods no longer use JSON. This will eliminate exceptions relating to JSON errors previously common to certain models.

- Base agent instructions template is not added to a job if no agent is used with a survey (reducing tokens).

- The `select()` method (for `Results` and `ScenarioList`) now allows partial match on key names to save typing.

### Fixed
- Bug in enforcement of token/rate limits.

- Bug in generation of exceptions report that excluded agent information.


## [0.1.32] - 2024-08-19
### Added
- Models: AWS Bedrock & Azure

- Question: New method `loop()` allows you to create versions of questions when you are constructing a survey. It takes a `ScenarioList()` as a parameter and returns a list of `Question` objects.

### Fixed
- Bug in `Survey` question piping prevented you from adding questions after piping.


## [0.1.31] - 2024-08-15

- `ScenarioList.from_sqlite` allows you to create a list of scenarios from a SQLite table.

- Added LaTeX support to SQL outputs and ability to write to files: `Results.print(format="latex", filename="example.tex")`

- Options that we think of as "terminal", such as `sql()`, `print()`, `html()`, etc., now take a `tee` boolean that causes them to return `self`. This is useful for chaining, e.g., if you run `print(format = "rich", tee = True)` it will return `self`, which allows you do also run `print(format = "rich", tee = True).print(format = "latex", filename = "example.tex")`.


## [0.1.30] - 2024-07-28
### Added
- Ability to create a `Scenario` for `question_options`. Example:
```
from edsl import QuestionMultipleChoice, Scenario

q = QuestionMultipleChoice(
    question_name = "capital_of_france",
    question_text = "What is the capital of France?", 
    question_options = "{{question_options}}"
)

s = Scenario({'question_options': ['Paris', 'London', 'Berlin', 'Madrid']})

results = q.by(s).run()
```


## [0.1.29] - 2024-07-21
### Added
- Prompts visibility: Call `prompts()` on a `Jobs` object for a survey to inspect the prompts that will be used in a survey before running it. For example:
```
from edsl import Model, Survey
j = Survey.example().by(Model()) 
j.prompts().print(format="rich")
```

- Piping: Use agent traits and components of questions (question_text, answer, etc.) as inputs to other questions in a survey (e.g., `question_text = "What is your last name, {{ agent.first_name }}?"` or `question_text = "Name some examples of {{ prior_q.answer }}"` or `question_options = ["{{ prior_q.answer[0]}}", "{{ prior_q.answer[1] }}"]`). Examples: https://docs.expectedparrot.com/en/latest/surveys.html#id2

- Agent traits: Call agent traits directly (e.g., `Agent.example().age` will return `22`).

### Fixed
- A bug in piping to allow you to pipe an `answer` into `question_options`. Examples: https://docs.expectedparrot.com/en/latest/surveys.html#id2


## [0.1.28] - 2024-07-09
### Added
- Method `add_columns()` allows you to add columns to `Results`.

- Class `ModelList` allows you to create a list of `Model` objects, similar to `ScenarioList` and `AgentList`.

### Changed
### Fixed
### Deprecated
### Removed


## [0.1.27] - 2024-06-28
### Added
- `Conjure` module allows you to import existing survey data and reconstruct it as EDSL objects. 
See details on methods `to_survey()`, `to_results()`, `to_agent_list()` and renaming/modifying objects: https://docs.expectedparrot.com/en/latest/conjure.html

### Changed
- Method `rename()` allows you to rename questions, agents, scenarios, results.

### Fixed
- New language models from OpenAI, Anthropic, Google will be added automatically when they are released by the platforms.


## [0.1.26] - 2024-06-10
### Fixed
- Removed an errant break point in language models module.


## [0.1.25] - 2024-06-10
### Added
- `Scenario.rename()` allows you to rename fields of a scenario.

- `Scenario.chunk()` allows you to split a field into chunks of a given size based on `num_word` or `num_lines`, creating a `ScenarioList`.

- `Scenario.from_html()` turns the contents of a website into a scenario.

- `Scenario.from_image()` creates an image scenario to use with a vision model (e.g., GPT-4o).

- `ScenarioList.sample()` allows you to take a sample from a scenario list.

- `ScenarioList.tally()` allows you to tally fields in scenarios.

- `ScenarioList.expand()` allows you to expand a scenario by a field in it, e.g., if a scenario field contains a list the method can be used to break it into separate scenarios.

- `ScenarioList.mutate()` allows you to add a key/value to each scenario.

- `ScenarioList.order_by()` allows you to order the scenarios.

- `ScenarioList.filter()` allows you to filter the scenarios based on a logical expression.

- `ScenarioList.from_list()` allows you to create a ScenarioList from a list of values and specified key.

- `ScenarioList.add_list()` allows you to use a list to add values to individual scenarios.

- `ScenarioList.add_value()` allows you to add a value to all the scenarios.

- `ScenarioList.to_dict()` allows you to turn a ScenarioList into a dictionary.

- `ScenarioList.from_dict()` allows you to create a ScenarioList from a dictionary.

- `Results.drop()` complements `Results.select()` for identifying the components that you want to print in a table. 

- `ScenarioList.drop()` similarly complements `ScenarioList.select()`.

### Changed
- Improvements to exceptions reports: Survey run exceptions now include the relevant job components and are optionally displayed in an html report.


## [0.1.24] - 2024-05-28
### Added 
- We started a blog! https://blog.expectedparrot.com

- `Agent`/`AgentList` method `remove_trait(<trait_key>)` allows you to remove a trait by name. This can be useful for comparing combinations of traits.

- `Agent`/`AgentList` method `translate_traits(<codebook_dict>)` allows you to modify traits based on a codebook passed as dictionary. Example:
```
agent = Agent(traits = {"age": 45, "hair": 1, "height": 5.5})
agent.translate_traits({"hair": {1:"brown"}})
```
This will return: `Agent(traits = {'age': 10, 'hair': 'brown', 'height': 5.5})`

- `AgentList` method `get_codebook(<filename>)` returns the codebook for a CSV file.

- `AgentList` method `from_csv(<filename>)` loads an `AgentList` from a CSV file with the column names as `traits` keys. Note that the CSV column names must be valid Python identifiers (e.g., `current_age` and not `current age`).

- `Results` method `to_scenario_list()` allows you to turn any components of results into a list of scenarios to use with other questions. A default parameter `remove_prefixes=True` will remove the results component prefixes `agent.`, `answer.`, `comment.`, etc., so that you don't have to modify placeholder names for the new scenarios. Example: https://docs.expectedparrot.com/en/latest/scenarios.html#turning-results-into-scenarios

- `ScenarioList` method `to_agent_list()` converts a `ScenarioList` into an `AgentList`. 

- `ScenarioList` method `from_pdf(<filename>)` allows you to import a PDF and automatically turn the pages into a list of scenarios. Example: https://docs.expectedparrot.com/en/latest/scenarios.html#turning-pdf-pages-into-scenarios

- `ScenarioList` method `from_csv(<filename>)` allows you to import a CSV and automatically turn the rows into a list of scenarios. 

- `ScenarioList` method `from_pandas(<dataframe>)` allows you to import a pandas dataframe and automatically turn the rows into a list of scenarios. 

- `Scenario` method `from_image(<image_path>)` creates a scenario with a base64 encoding of an image. The scenario is formatted as follows: `"file_path": <filname / url>, "encoded_image": <generated_encoding>`
Note that you need to use a vision model (e.g., `model = Model('gpt-4o')`) and you do *not* need to add a `{{ placeholder }}` for the scenario (for now--this might change!).
Example:
```
from edsl.questions import QuestionFreeText
from edsl import Scenario, Model

model = Model('gpt-4o')

scenario = Scenario.from_image('general_survey.png') # Image from this notebook: https://docs.expectedparrot.com/en/latest/notebooks/data_labeling_agent.html 
# scenario

q = QuestionFreeText(
    question_name = "example",
    question_text = "What is this image showing?" # We do not need a {{ placeholder }} for this kind of scenario
)

results = q.by(scenario).by(model).run(cache=False)

results.select("example").print(format="rich")
```
Returns:
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ answer                                                                                                          ┃
┃ .example                                                                                                        ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ This image is a flowchart showing the process of creating and administering a survey for data labeling tasks.   │
│ The steps include importing data, creating data labeling tasks as questions about the data, combining the       │
│ questions into a survey, inserting the data as scenarios of the questions, and administering the same survey to │
│ all agents.                                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Changed
- `Question` and `Survey` method `html()` generates an improved html page representation of the object. You can optionally specify the filename and css. See default css: https://github.com/expectedparrot/edsl/blob/9d981fa25a0dd83e6cca4d17bcb9316a3d452a64/edsl/surveys/SurveyExportMixin.py#L10

- `QuestionMultipleChoice` now takes numbers and lists as `question_options` (e.g., `question_options = [[1,2,3], [4,5,6]]` is allowed). Previously options had to be a list of strings (i.e., `question_options = ['1','2','3']` is still allowed but not required). 

## [0.1.23] - 2024-05-18 
### Added 
- Optional parameter in `Results` method `to_list()` to flatten a list of lists (eg, responses to `QuestionList`): `results.to_list(flatten=True)`

### Fixed
- Erroneous error messages about adding rules to a survey.

## [0.1.22] - 2024-05-14
### Added
- New `Survey` method to export a survey to file. Usage: `generated_code = survey.code("example.py")`

### Fixed
- A bug in `Survey` method `add_skip_logic()`

## [0.1.21] - 2024-05-13
### Added 
- New methods for adding, sampling and shuffling `Results` objects: 
   `dup_results = results + results`
   `results.shuffle()`
   `results.sample(n=5)`

### Changed
- Optional parameter `survey.run(cache=False)` if you do not want to access any cached results in running a survey.

- Instructions passed to an agent at creation are now a column of results: `agent_instruction`

## [0.1.20] - 2024-05-09
### Added 
- <b>Methods for setting session caches</b>
New function `set_session_cache` will set the cache for a session:

```
from edsl import Cache, set_session_cache
set_session_cache(Cache())
```
The cache can be set to a specific cache object, or it can be set to a dictionary or SQLite3Dict object:
```
from edsl import Cache, set_session_cache
from edsl.data import SQLiteDict
set_session_cache(Cache(data = SQLiteDict("example.db")))
# or
set_session_cache(Cache(data = {}))
```
The `unset_session_cache` function is used to unset the cache for a session:
```
from edsl import unset_session_cache
unset_session_cache()
```
This will unset the cache for the current session, and you will need to pass the cache object to the run method during the session.

Details: https://docs.expectedparrot.com/en/latest/data.html#setting-a-session-cache

### Changed
- <b>Answer comments are now a separate component of results</b>
The "comment" field that is automatically added to each question (other than free text) is now stored in `Results` as `comment.<question_name>`. Prior to this change, the comment for each question was stored as `answer.<question_name>_comment`, i.e., if you ran `results.columns` the list of columns would include `answer.<question_name>` and `answer.<question_name>_comment` for each question. With this change, the columns will now be `answer.<question_name>` and `comment.<question_name>_comment`. This change is meant to make it easier to select only the answers, e.g., running `results.select('answer.*').print()` will no longer also include all the comments, which you may not want to display.
(The purpose of the comments field is to allow the model to add any information about its response to a question, which can help avoid problems with JSON formatting when the model does not want to return <i>just</i> the properly formatted response.)

- <b>Exceptions</b>
We modified exception messages. If your survey run generates exceptions, run `results.show_exceptions()` to print them in a table.

### Fixed
- A package that was missing for working with Anthropic models.

## [0.1.19] - 2024-05-03
### Added
- `Results` objects now include columns for question components. Call the `.columns` method on your results to see a list of all components. Run `results.select("question_type.*", "question_text.*", "question_options.*").print()` to see them.

- `Survey` objects now also have a `.to_csv()` method.

### Changed 
- Increased the maximum number of multiple choice answer options to 200 (previously 20) to facilitate large codebooks / data labels.

## [0.1.18] - 2024-05-01
### Fixed
- A bug in in `Survey.add_rule()` method that caused an additional question to be skipped when used to apply a skip rule.

## [0.1.17] - 2024-04-29
### Added
- <b>New models:</b> Run `Model.available()` to see a complete current list.

### Fixed
- A bug in json repair methods.

## [0.1.16] - 2024-04-11
### Added
- <b>New documentation:</b> https://docs.expectedparrot.com

- <b>Progress bar:</b> 
You can now pass `progress_bar=True` to the `run()` method to see a progress bar as your survey is running. Example:
```
from edsl import Survey 
results = Survey.example().run(progress_bar=True)

                            Job Status                             
                                                                   
  Statistic                                            Value       
 ───────────────────────────────────────────────────────────────── 
  Elapsed time                                         1.1 sec.    
  Total interviews requested                           1           
  Completed interviews                                 1           
  Percent complete                                     100 %       
  Average time per interview                           1.1 sec.    
  Task remaining                                       0           
  Estimated time remaining                             0.0 sec.    
  Model Queues                                                     
  gpt-4-1106-preview;TPM (k)=1200.0;RPM (k)=8.0                    
  Number question tasks waiting for capacity           0           
   new token usage                                                 
   prompt_tokens                                       0           
   completion_tokens                                   0           
   cost                                                $0.00000    
   cached token usage                                              
   prompt_tokens                                       104         
   completion_tokens                                   35          
   cost                                                $0.00209    
```

- <b>New language models</b>: 
We added new models from Anthropic and Databricks. To view a complete list of available models see <a href="https://docs.expectedparrot.com/en/latest/enums.html#edsl.enums.LanguageModelType">edsl.enums.LanguageModelType</a> or run:
```python
from edsl import Model
Model.available()
```
This will return:
```python
['claude-3-haiku-20240307', 
'claude-3-opus-20240229', 
'claude-3-sonnet-20240229', 
'dbrx-instruct', 
'gpt-3.5-turbo',
'gpt-4-1106-preview',
'gemini_pro',
'llama-2-13b-chat-hf',
'llama-2-70b-chat-hf',
'mixtral-8x7B-instruct-v0.1']
```
For instructions on specifying models to use with a survey see new documentation on <a href="https://docs.expectedparrot.com/en/latest/language_models.html">Language Models</a>.
<i>Let us know if there are other models that you would like us to add!</i>

### Changed
- <b>Cache:</b> 
We've improved user options for caching LLM calls. 

<i>Old method:</i>
Pass a `use_cache` boolean parameter to a `Model` object to specify whether to access cached results for the model when using it with a survey (i.e., add `use_cache=False` to generate new results, as the default value is True).

<i>How it works now:</i>
All results are (still) cached by default. To avoid using a cache (i.e., to generate fresh results), pass an empty `Cache` object to the `run()` method that will store everything in it. This can be useful if you want to isolate a set of results to share them independently of your other data. Example:
```
from edsl.data import Cache
c = Cache() # create an empty Cache object

from edsl.questions import QuestionFreeText
results = QuestionFreeText.example().run(cache = c) # pass it to the run method

c # inspect the new data in the cache
```
We can inspect the contents:
```python
Cache(data = {‘46d1b44cd30e42f0f08faaa7aa461d98’: CacheEntry(model=‘gpt-4-1106-preview’, parameters={‘temperature’: 0.5, ‘max_tokens’: 1000, ‘top_p’: 1, ‘frequency_penalty’: 0, ‘presence_penalty’: 0, ‘logprobs’: False, ‘top_logprobs’: 3}, system_prompt=‘You are answering questions as if you were a human. Do not break character. You are an agent with the following persona:\n{}’, user_prompt=‘You are being asked the following question: How are you?\nReturn a valid JSON formatted like this:\n{“answer”: “<put free text answer here>“}‘, output=’{“id”: “chatcmpl-9CGKXHZPuVcFXJoY7OEOETotJrN4o”, “choices”: [{“finish_reason”: “stop”, “index”: 0, “logprobs”: null, “message”: {“content”: “```json\\n{\\“answer\\“: \\“I\‘m doing well, thank you for asking! How can I assist you today?\\“}\\n```“, “role”: “assistant”, “function_call”: null, “tool_calls”: null}}], “created”: 1712709737, “model”: “gpt-4-1106-preview”, “object”: “chat.completion”, “system_fingerprint”: “fp_d6526cacfe”, “usage”: {“completion_tokens”: 26, “prompt_tokens”: 68, “total_tokens”: 94}}’, iteration=0, timestamp=1712709738)}, immediate_write=True, remote=False)
```
For more details see new documentation on <a href="https://docs.expectedparrot.com/en/latest/data.html">Caching LLM Calls</a>.

<i>Coming soon: Automatic remote caching options.</i>

- <b>API keys:</b> 
You will no longer be prompted to enter your API keys when running a session. We recommend storing your keys in a private `.env` file in order to avoid having to enter them at each session. Alternatively, you can still re-set your keys whenever you run a session. See instructions on setting up an `.env` file in our <a href="https://docs.expectedparrot.com/en/latest/starter_tutorial.html#part-1-using-api-keys-for-llms">Starter Tutorial</a>.

<i>The Expected Parrot API key is coming soon! It will let you access all models at once and come with automated remote caching of all results. If you would like to test it out, please let us know!</i>

- <b>Prompts:</b> 
We made it easier to modify the agent and question prompts that are sent to the models.
For more details see new documentation on <a href="https://docs.expectedparrot.com/en/latest/prompts.html">Prompts</a>.

### Deprecated
- `Model` attribute `use_cache` is now deprecated. See details above about how caching now works.

### Fixed
- `.run(n = ...)` now works and will run your survey with fresh results the specified number of times.

## [0.1.15] - 2024-03-09
### Fixed
- Various fixes and small improvements

## [0.1.14] - 2024-03-06
### Added
- The raw model response is now available in the `Results` object, accessed via "raw_model_response" keyword. 
There is one for each question. The key is the question_name + `_raw_response_model`
- The `.run(progress_bar = True)` returns a much more informative real-time view of job progress.

## [0.1.13] - 2024-03-01
### Added
- The `answer` component of the `Results` object is printed in a nicer format.

### Fixed
- `trait_name` descriptor was not working; it is now fixed.
- `QuestionList` is now working properly again

## [0.1.12] - 2024-02-12
### Added
- Results now provides a `.sql()` method that can be used to explore data in a SQL-like manner.
- Results now provides a `.ggplot()` method that can be used to create ggplot2 visualizations.
- Agent now admits an optional `name` argument that can be used to identify the Agent.

### Fixed
- Fixed various issues with visualizations. They should now work better.

## [0.1.11] - 2024-02-01
### Fixed
- Question options can now be 1 character long or more (down from 2 characters)
- Fixed a bug where prompts displayed were incorrect (prompts sent were correct)

## [0.1.9] - 2024-01-27
### Added
- Report functionalities are now part of the main package.

### Fixed
- Fixed a bug in the Results.print() function

### Removed
- The package no longer supports a report extras option.
- Fixed a bug in EndofSurvey

## [0.1.8] - 2024-01-26
### Fixed
- Better handling of async failures
- Fixed bug in survey logic

## [0.1.7] - 2024-01-25
### Fixed
- Improvements in async survey running
- Added logging

## [0.1.6] - 2024-01-24
### Fixed
- Improvements in async survey running

## [0.1.5] - 2024-01-23
### Fixed
- Improvements in async survey running

## [0.1.4] - 2024-01-22
### Added
- Support for several large language models
- Async survey running
- Asking for API keys before they are used

### Fixed
- Bugs in survey running
- Bugs in several question types 

### Removed
- Unused files
- Unused package dependencies

## [0.1.1] - 2023-12-24
### Added
- Changelog file

### Fixed
- Image display and description text in README.md

### Removed
- Unused files

## [0.1.0] - 2023-12-20
### Added
- Base feature
