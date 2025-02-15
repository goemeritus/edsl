.. _index:

Expected Parrot: Tools for AI-Powered Research
==============================================

Expected Parrot delivers powerful tools for conducting research with human and artificial intelligences.

This page provides documentation for **Expected Parrot Domain-Specific Language (EDSL)**, a Python package for performing research with AI agents and language models,
and **Coop**, a platform for creating, storing and sharing AI-based research projects.

* EDSL is available to download from `PyPI <https://pypi.org/project/edsl/>`_ (run `pip install edsl`). The source code is available at `GitHub <https://github.com/expectedparrot/edsl>`_.
* `Create an account <https://www.expectedparrot.com/login>`_ to post and share content, run surveys and store results at the Expected Parrot survey. Learn more about `how it works <https://docs.expectedparrot.com/en/latest/coop.html>`_ and start `exploring <https://www.expectedparrot.com/content/explore>`_.


Key features 
------------

Simplified access to hundreds of models
   A single API key lets you conduct research with many popular models at once. `Learn more <https://docs.expectedparrot.com/en/latest/remote_inference.html>`_.

Collaboration features
   Use `Coop <https://www.expectedparrot.com/content/explore>`_ to create, store and share your research projects seamlessly.

Data integrations
   Easily import, analyze and extend many types of data. `Learn more <https://docs.expectedparrot.com/en/latest/scenarios.html>`_.

Hybrid human-AI surveys
   Collect and combine responses from humans and AI. `Learn more <https://docs.expectedparrot.com/en/latest/survey_builder.html>`_.

Built-in analysis tools
   Readily visualize, analyze and compare responses. `Learn more <https://docs.expectedparrot.com/en/latest/results.html>`_.


Use cases 
---------

Our tools simplify survey creation, experiment execution and response analysis. 
Common use cases include:

Data labeling
   Use AI to answer qualitative and quantitative questions about your data, and extract insights. See `examples <https://docs.expectedparrot.com/en/latest/notebooks/data_labeling_example.html>`_.

Market research
   Gather insights on consumer preferences, behaviors and trends. Simulate customer personas with AI agents and analyze their responses. See `examples <https://docs.expectedparrot.com/en/latest/notebooks/yoga_studio_name_survey.html>`_.

User experience research
   Assess user satisfaction, usability and engagement. Use AI agents to simulate user profiles and analyze their feedback on products or services. See `examples <https://docs.expectedparrot.com/en/latest/notebooks/nps_survey.html>`_.

Integrate human and AI data
   Combine human responses with AI-generated responses to create richer datasets. See `examples <https://docs.expectedparrot.com/en/latest/notebooks/import_agents.html>`_.

Analyze survey data
   Analyze survey data with built-in methods. Simulate follow-up interviews with respondents. See `examples <https://docs.expectedparrot.com/en/latest/notebooks/analyze_evaluations.html>`_.

Social science research
   Explore hypotheses, gather qualitative or quantitative data and generate new data using AI. 

For more on EDSL's key features and use cases, visit the :ref:`overview` section.


Getting started 
---------------

To use EDSL, you need to install the package and choose how to access language models.
Please see the links in the steps below for more details:

1. **Install EDSL** 
   
   Run the following command to install the package:

   .. code:: 

      pip show edsl


   See :ref:`installation` instructions for more details.

2. **Create a Coop account** 

   `Create an account <https://www.expectedparrot.com/login>`_ to access the Expected Parrot server, free storage and special features and collaboration tools.

3. **Manage API keys for language models**

   Your account comes with a key that allows you to run surveys with all available models at the Expected Parrot server.
   You can also use and share your own keys from service providers.

   See instructions on :ref:`api_keys` for details and options.

4. **Run a survey.** 

   Read the :ref:`starter_tutorial` and `download a notebook <https://www.expectedparrot.com/content/179b3a78-2505-4568-acd9-c09d18953288>`_ to create a survey and run it.
   See examples for many use cases and `tips <https://docs.expectedparrot.com/en/latest/checklist.html>`_ on using EDSL effectively in the documentation.


Join our `Discord channel <https://discord.com/invite/mxAYkjfy9m>`_ to ask questions and chat with other users!


Researchers
-----------

Are you using EDSL for a research project?
Send an email to *info@expectedparrot.com* and we'll give you `credits <https://docs.expectedparrot.com/en/latest/credits.html>`_ to run your project!


Introduction
------------

- :ref:`overview`: An overview of the purpose, concepts and goals of the EDSL package.
- :ref:`whitepaper`: A whitepaper about the EDSL package (*in progress*).
- :ref:`citation`: How to cite the package in your work.
- :ref:`papers`: Research papers and articles that use or cite EDSL.


Core Concepts
-------------

- :ref:`questions`: Learn about different question types and applications.
- :ref:`scenarios`: Explore how questions can be dynamically parameterized for tasks like data labeling.
- :ref:`surveys`: Construct surveys with rules and conditions.
- :ref:`agents`: Design AI agents with relevant traits to respond to surveys.
- :ref:`language_models`: Select language models to generate results.


Working with Results
--------------------

- :ref:`results`: Access built-in methods for analyzing survey results as datasets.
- :ref:`caching`: Learn about caching and sharing results.
- :ref:`exceptions`: Identify and handle exceptions in running surveys.
- :ref:`token_usage`: Monitor token limits and usage for language models.


Coop 
----
 
`Coop <https://www.expectedparrot.com/content/explore>`_ is a platform for creating, storing and sharing AI-based research.
It is fully integrated with EDSL and provides access to special features for working with AI agents and language models, free storage and collaboration tools, including:

- :ref:`survey_builder`: A user-friendly no-code interface for creating surveys and gathering responses from humans and AI agents.
- :ref:`remote_inference`: Access all available language models and run surveys at the Expected Parrot server. 
- :ref:`remote_caching`: Automatically store results and API calls at the Expected Parrot server. 
- :ref:`notebooks` & :ref:`colab_notebooks`: Easily post and share `.ipynb` and `.py` files to the Coop and access with Colab. 
- :ref:`filestore`: Store and share data files for use in EDSL projects.

Learn more about `how it works <https://docs.expectedparrot.com/en/latest/coop.html>`_ and purchasing `credits <https://docs.expectedparrot.com/en/latest/credits.html>`_.


.. Importing Surveys
.. -----------------

.. - :ref:`conjure`: Automatically import other survey data into EDSL to:
  
..   * Clean and analyze your data
..   * Create AI agents and conduct follow-on interviews
..   * Extend results with new questions
..   * Store and share data at the Coop


How-to Guides & Notebooks
-------------------------

Examples of special methods and use cases for EDSL, including:

- Data labeling
- Data cleaning
- Analyzing survey results 
- Adding data to surveys from CSVs, PDFs, images and other sources
- Conducting agent conversations
- Converting surveys into EDSL
- Cognitive testing 
- Research methods

 
Links
-----

- Download the current version of EDSL at `PyPI <https://pypi.org/project/edsl>`_.
- Get the latest EDSL updates at `GitHub <https://github.com/expectedparrot/edsl>`_.
- Create a `Coop account <https://www.expectedparrot.com/login>`_.
- Join the `Discord channel <https://discord.com/invite/mxAYkjfy9m>`_.
- Follow on social media: `Twitter/X <https://twitter.com/expectedparrot>`_, `LinkedIn <https://www.linkedin.com/company/expectedparrot>`_, `Blog <https://blog.expectedparrot.com>`_
- Send an email: *info@expectedparrot.com*


.. toctree::
   :maxdepth: 2
   :caption: Introduction
   :hidden:

   overview
   whitepaper
   papers

.. toctree::
   :maxdepth: 2
   :caption: Getting Started
   :hidden:

   getting_started
   installation
   api_keys
   remote_inference
   remote_caching
   starter_tutorial
   colab_setup

.. toctree::
   :maxdepth: 2
   :caption: Core Concepts
   :hidden:

   questions
   scenarios
   surveys
   agents
   prompts
   language_models

.. toctree::
   :maxdepth: 2
   :caption: Working with Results
   :hidden:

   results
   data
   exceptions
   token_usage
   checklist

.. toctree::
   :maxdepth: 2
   :caption: Coop
   :hidden:

   coop
   credits
   filestore
   notebooks
   colab_notebooks
   survey_builder

.. toctree::
   :maxdepth: 2
   :caption: How-to Guides
   :hidden:

   notebooks/edsl_intro.ipynb
   notebooks/estimating_costs.ipynb
   notebooks/piping_comments.ipynb
   notebooks/looping_and_piping.ipynb
   notebooks/answering_instructions_example.ipynb
   notebooks/image_scenario_example.ipynb
   notebooks/analyze_customer_call.ipynb
   notebooks/updating_agents.ipynb
   notebooks/save_load_objects_locally.ipynb
   notebooks/data_labeling_example.ipynb
   notebooks/data_cleaning.ipynb
   notebooks/yoga_studio_name_survey.ipynb
   notebooks/scenario_from_pdf.ipynb
   notebooks/scenario_list_wikipedia.ipynb
   notebooks/scenarios_filestore_example.ipynb
   notebooks/adding_metadata.ipynb
   notebooks/question_loop_scenarios.ipynb
   notebooks/skip_logic_scenarios.ipynb
   notebooks/example_agent_dynamic_traits.ipynb
   notebooks/import_agents.ipynb
   notebooks/batching_results.ipynb
   notebooks/research_methods.ipynb
   notebooks/agent_fatigue.ipynb
   notebooks/model_test_report.ipynb
   notebooks/run_background.ipynb

.. toctree::
   :maxdepth: 2
   :caption: Notebooks
   :hidden:

   notebooks/next_token_probs.ipynb
   notebooks/summarizing_transcripts.ipynb
   notebooks/analyze_evaluations.ipynb
   notebooks/concept_induction.ipynb
   notebooks/conduct_interview.ipynb
   notebooks/qualitative_research.ipynb
   notebooks/nps_survey.ipynb
   notebooks/data_labeling_agent.ipynb
   notebooks/scenariolist_unpivot.ipynb
   notebooks/random_numbers.ipynb
   notebooks/testing_training_data.ipynb
   notebooks/evaluating_job_posts.ipynb
   notebooks/explore_llm_biases.ipynb
   notebooks/research_random_silicon_sampling.ipynb
   notebooks/explore_survey_contexts.ipynb
   notebooks/free_responses.ipynb
   notebooks/digital_twin.ipynb
   notebooks/writing_style.ipynb
   notebooks/google_form_to_edsl.ipynb
   notebooks/edsl_polling.ipynb
   notebooks/ces_data_edsl.ipynb

.. toctree::
   :maxdepth: 2
   :caption: Developers
   :hidden:

   contributing
   interview
   jobs 
   interviews
   answers
   enums
