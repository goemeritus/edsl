.. _api_keys:

API Keys
========

API keys are required to access the services of large language models (LLMs) such as OpenAI's GPTs, Google's Gemini, Anthropic's Claude, Llama 2, Groq and others.

To access LLMs with EDSL you can either use *remote inference* or *local inference*.
Remote inference allows you to run surveys on the Expected Parrot server with available models while local inference allows you to run surveys on your own machine using your own API keys for models.


| ***Special note for Colab users:***
| If you are using EDSL in a Colab notebook, please see `special instructions <https://docs.expectedparrot.com/en/latest/colab_setup.html>`_ on storing API keys as "secrets" in lieu of storing them in a `.env` file as described below (:ref:`colab_setup`).


Remote inference 
^^^^^^^^^^^^^^^^

This method allows you to purchase credits to run EDSL surveys on the Expected Parrot server instead of your local machine, and avoid managing your own API keys for different LLM providers.

To use remote inference you must activate it at your `Coop <https://www.expectedparrot.com/home/api>`_ account and store your Expected Parrot API key in a `.env` file in your EDSL working directory.
Your `.env` file should include the following line (replace `your_key_here` with your actual Expected Parrot API key from your Coop account):

.. code-block:: python

   EXPECTED_PARROT_API_KEY='your_key_here'


Please see the :ref:`remote_inference` section for more details on how to use remote inference with EDSL, and the `Credits <https://docs.expectedparrot.com/en/latest/credits.html>`_ section for information on purchasing and calculating credit costs.


Local inference 
^^^^^^^^^^^^^^^

You can access LLMs with EDSL on your own machine by providing your own API keys for LLMs.
There are two ways of providing your own API keys to EDSL:


**1. Using a .env file (recommended)**

Create a `.env` file in your EDSL working directory and populate it with your API keys.
Replace `your_key_here` with your actual API key for each service that you plan to use:

.. code-block:: python

   ANTHROPIC_API_KEY='your_key_here'
   DEEP_INFRA_API_KEY='your_key_here'
   GOOGLE_API_KEY='your_key_here'
   GROQ_API_KEY='your_key_here'
   MISTRAL_API_KEY='your_key_here'
   OPENAI_API_KEY='your_key_here'
   REPLICATE_API_KEY='your_key_here'


AWS Bedrock requires multiple keys:

.. code-block:: python

   AWS_ACCESS_KEY_ID='your_key_here'
   AWS_SECRET_ACCESS_KEY='your_key_here'
   AZURE_ENDPOINT_URL_AND_KEY='your_key_here'


Using a `.env file` allows you to store your keys once and avoid repeatedly enter your API keys each time you start a session with EDSL.


**2. Setting API keys in your Python code**

Alternatively, you can directly set your API keys in your Python script before importing any EDSL objects. 
This method stores the keys in your system's memory only for the duration of the session:

.. code-block:: python

   import os

   os.environ['ANTHROPIC_API_KEY'] = 'your_key_here'
   os.environ['DEEP_INFRA_API_KEY'] = 'your_key_here'
   os.environ['GOOGLE_API_KEY'] = 'your_key_here'
   os.environ['GROQ_API_KEY'] = 'your_key_here'
   os.environ['MISTRAL_API_KEY'] = 'your_key_here'
   os.environ['OPENAI_API_KEY'] = 'your_key_here'
   os.environ['REPLICATE_API_KEY'] = 'your_key_here'


Remember, if you restart your session, you will need to re-enter your API keys.
It is also important to remove your API keys from your code before sharing it with others.


Caution
~~~~~~~

Treat your API keys as sensitive information, akin to passwords. 
Never share them publicly or upload files containing your API keys to public repositories.


Troubleshooting
~~~~~~~~~~~~~~~

In addition to API keys, you must also have credits available on your account with a language model provider in order to run surveys with some models.
(If you are using remote inference, simply ensure that you have credits on your Expected Parrot account.)

If you do not specify a model to use for a survey, EDSL will attempt to run it with the default model.
In practice, this means that the following sets of commands are equivalent:

*Version 1*:

.. code-block:: python

   from edsl import Survey 

   results = Survey.example().run()


*Version 2*:

.. code-block:: python

   from edsl import Survey, Model 

   results = Survey.example().by(Model()).run() 


*Version 3*:

.. code-block:: python

   from edsl import Survey, Model 

   s = Survey.example()
   m = Model()

   results = s.by(m).run()


If you have not provided an API key for the default model you will receive an error message about an exception.
You may also receive an error message if you do not have credits on your account with the model provider.
A common exception for this problem is an `AuthenticationError` about API keys: `Incorrect API key provided...`

To resolve this issue, you can either provide the correct API key for the default model (and ensure that you have credits from the provider) or specify a different model to use for the survey.

See more information on the available models in the  :ref:`language_models` section of the documentation.


Please also feel free to reach out to us to help you troubleshoot:

* Discord channel: https://discord.com/invite/mxAYkjfy9m
* Email: info@expectedparrot.com
