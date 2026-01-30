BAM: Build a model

BAM is used to create a multi-colored, multidimensional design graph model.

BAM provides an ingestion chain to do this via existing information. Ingestion
can be done through hardcoded parsers (standard/incremental pipelines) or
through an LLM-driven agent pipeline that analyses incoming data and produces
a transform plan automatically.

The generated model can then be accessed by AI agents with very high speed and precision to answer questions incorporating all colors if needed.

BAM should be a stand-alone tool that agents can use to work on digital
  twins for multiple projects in parallel. I imagine the following process: A user (human+agent) read bam. The AI
  reads the documentation, understands the process, get's hints to create the model. Then the agent and human discuss
  the project. They besically develop the sketch together (again, with help of hints from BAM) and come up with an
  ingestion plan (which parts are ingested first, which ones later, which extractors are used, ....). This ingestion
  plan then defines how to use the tools of bam in which order, which checks to do, ...



