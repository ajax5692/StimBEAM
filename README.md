# StimBEAM (Stimulation, Behavioral and Ensemble Activity Mapping)

⚙️🏗️ **Development in Progress**

**StimBEAM** (formerly PStim Data Analysis Pipeline or PStim_DAP) is a modular Django-based framework for managing experimental metadata and selected background data-analysis workflows for laboratory neuroscience projects. I named the current pipeline like this for now, as I will be primarily using this for my own experimental works, but subject to lab feedback, I plan to scale it up for other lab groups, hence the modular approach in designing it.

The project is designed around independent experimental domains so that different research groups can use only the components relevant to their workflow.

For example:

- an **imaging-only group** can use animal and imaging metadata without behavioral training;
- a **behavioral-training group** can use animal and training metadata without imaging;
- the complete local workflow can combine animal, virus, imaging, imaging-analysis, and training modules.

The current development deployment uses a **PostgreSQL database running in Docker on a local workstation**. The architecture is intended to be scalable toward lab-group or institutional deployments using containerized services and deployment-specific configuration.

---

## Project Goals

StimBEAM aims to provide a common framework for:

- structured experimental metadata management;
- linking experimental records across animals, imaging, training, and viral manipulations;
- tracking large experimental files without storing those files directly in the database;
- maintaining historical records and change tracking;
- running selected scientific analyses as background jobs;
- keeping experimental domains sufficiently independent that groups can deploy only the modules they require;
- providing a path from local workstation development toward containerized lab or institutional deployment.

---

## Modular Architecture

The repository currently contains five main experimental metadata domains:

| App | Purpose |
| --- | --- |
| `animals_metadata` | Core animal records, vision checks, viral injection records, experimental ownership/status information, and change history |
| `virus_metadata` | Virus inventory metadata including virus ID, construct, titre, storage location, owner, and history |
| `imaging_metadata` | Imaging-session metadata including animal linkage, acquisition date, imaging region, source MESC file path, measurement-unit ranges, and notes |
| `imaging_analysis_metadata` | Optional protocol-specific imaging-analysis workflow with background processing and analysis-job tracking |
| `training_metadata` | Optional behavioral-training metadata, BPod data references, body-weight tracking, training-data processing, and analysis outputs |

The intended dependency structure is approximately:

```text
                         animals_metadata
                         /              \
                        /                \
                       ↓                  ↓
              imaging_metadata      training_metadata
                       │                  │
                       ↓                  │
       imaging_analysis_metadata          │
              [optional]                  │
                                          ↓
                              training_data_processing
                              [internal processing package]


virus_metadata
      ↑
      │
viral injection records
in animals_metadata
```

The important architectural principle is that optional experimental domains should remain independent whenever possible.

For example:

```text
Imaging does not require Training.

Training does not require Imaging.

Training-data processing does not require Imaging Analysis.
```

---

## Animals Metadata

`animals_metadata` provides the central animal records used by other experimental domains.

Current metadata includes information such as:

- Animal ID
- Owner
- Sex
- Genotype
- Cage ID
- Project ID
- Date of birth
- Calculated age
- Animal status (live/dead)

The app also manages additional animal-associated experimental records including:

### Vision Checks

Vision-check records can associate an animal with:

- vision-test type;
- test result;
- associated data path.

### Viral Injections

Viral injection records associate experimental animals with virus inventory entries and injection metadata.

The current model supports multiple injections associated with a record, including information such as:

- Virus ID
- Injection volume
- Injection site
- Injection depth
- Injection date
- Injecting person
- Surgery information
- Notes
- Expression information

Virus identity is linked to the dedicated `virus_metadata` inventory.

---

## Virus Metadata

`virus_metadata` provides a centralized virus inventory rather than defining virus information independently inside individual experimental records.

Current virus metadata includes:

- Virus ID
- Viral construct
- Titre
- Virus owner

Viral injection records in `animals_metadata` reference this inventory.

This separation allows virus information to be maintained centrally while experimental records describe how a virus was actually used.

---

## Imaging Metadata

`imaging_metadata` stores metadata associated with imaging acquisitions.

An imaging session currently includes:

- associated animal;
- acquisition date;
- imaging region;
- source `.mesc` file path;
- measurement-unit ranges;
- notes.

The database stores the **location and metadata of the experimental file**, rather than storing the large imaging dataset itself.

Conceptually:

```text
PostgreSQL
    │
    └── ImagingSession
            │
            ├── Animal
            ├── Acquisition date
            ├── Imaging region
            ├── MESC file path
            └── Measurement-unit ranges

Experimental PC/server storage
    │
    └── actual .mesc data
```

This keeps the relational database focused on searchable metadata while large scientific datasets remain on appropriate laboratory storage.

---

## Imaging Analysis Metadata

`imaging_analysis_metadata` is an **optional, protocol-specific extension** of the imaging domain.

It is currently designed for the local imaging-analysis workflow and is not required for groups that only want to manage imaging metadata.

An analysis job is associated with an `ImagingSession` and follows a defined processing lifecycle:

```text
PENDING
   │
   ▼
RUNNING
   │
   ├──────────────► FAILED
   │
   ▼
COMPLETED
```

Analysis records can store information such as:

- linked imaging session;
- processing status;
- detected frame rate;
- analysis parameters;
- start and completion times;
- output directory;
- log path;
- notes;
- failure/error information.

### Imaging Analysis Worker

Long-running imaging analysis is kept outside the normal Django web-request process.

The independent Django management-command worker:

```text
imaging_analysis_worker
```

looks for pending imaging-analysis jobs and processes them in the background.

Conceptually:

```text
Django / PostgreSQL
        │
        │ Pending AnalysisRun
        ▼
imaging_analysis_worker
        │
        ▼
Imaging analysis pipeline
        │
        ▼
Suite2P-based processing
        │
        ▼
Results / logs
        │
        ▼
PostgreSQL
        │
        └── COMPLETED / FAILED
```

The imaging-analysis implementation is intentionally allowed to remain specific to the imaging protocol for which it was developed.

Other research groups can use `imaging_metadata` without using this analysis module.

---

## Training Metadata

`training_metadata` provides an independent behavioral-training domain.

It does **not** depend on the imaging workflow.

Training sessions currently contain information such as:

- associated animal;
- training date;
- source BPod `.mat` file path;
- training-unit range;
- processing status;
- output paths;
- calculated metrics;
- notes;
- processing errors.

Training jobs use the same general state model as imaging-analysis jobs:

```text
PENDING → RUNNING → COMPLETED

                  ↘ FAILED
```

This allows behavioral processing to run asynchronously rather than blocking the Django web interface.

---

## Training Data Processing

Scientific processing associated with training data is kept inside the training domain:

```text
training_metadata/
    │
    └── training_data_processing/
            │
            └── extract_licking.py
```

`training_data_processing` is an **internal Python package of `training_metadata`**, rather than a separate Django application.

The current behavioral processing includes extraction and analysis of licking-related data from behavioral training files.

The architecture leaves room for additional behavioral-processing operations in the future.

For example:

```text
training_metadata
       │
       ▼
training_data_processing
       │
       ├── licking extraction
       ├── behavioral metrics
       ├── trial-level analysis
       └── future behavioral processing
```

---

## Training Analysis Worker

Training-data analysis is handled by its own independent background worker:

```text
training_analysis_worker
```

Conceptually:

```text
TrainingSession
      │
      │ PENDING
      ▼
training_analysis_worker
      │
      ▼
training_data_processing
      │
      ▼
extract_licking
      │
      ├── plots
      ├── raster output
      ├── exported data
      └── calculated metrics
      │
      ▼
TrainingSession
      │
      └── COMPLETED / FAILED
```

The training worker and imaging-analysis worker are deliberately separate processes.

Therefore, a long-running imaging-analysis job does not need to block behavioral-data processing.

---

## Mouse Body-Weight Tracking

Body-weight tracking is part of the `training_metadata` domain because it is primarily associated with behavioral-training workflows such as water restriction.

The system supports longitudinal body-weight records associated with individual animals.

Conceptually:

```text
Animal
   │
   ▼
Mouse Body Weight Record
   │
   ├── Day 1 weight
   ├── Day 2 weight
   ├── Day 3 weight
   └── ...
```

Individual measurements can include:

- date;
- body weight in grams;
- body weight relative to the starting weight;
- notes.

Groups that do not perform behavioral training do not need this functionality.

---

## Independent Background Workers

The complete local workflow currently contains two conceptually independent processing systems:

```text
                        PostgreSQL
                       /          \
                      /            \
                     ▼              ▼
           Imaging analysis     Training analysis
                 job                  job
                  │                    │
                  ▼                    ▼
     imaging_analysis_worker   training_analysis_worker
                  │                    │
                  ▼                    ▼
        imaging pipeline       behavioral pipeline
                  │                    │
                  ▼                    ▼
              Suite2P          training_data_processing
                                       │
                                       ▼
                                 extract_licking
```

This separation is important for both processing independence and modular deployment.

---

## Example Modular Deployments

Different groups can use different subsets of the same repository.

### Imaging-Only Research Group

A group performing imaging without behavioral training could use:

```text
animals_metadata
        │
        ▼
imaging_metadata
```

It would not require:

```text
training_metadata
training_analysis_worker
training_data_processing
```

and it would only require `imaging_analysis_metadata` if the group's imaging protocol is compatible with that analysis workflow.

---

### Behavioral / Training Research Group

A group performing behavioral experiments without imaging could use:

```text
animals_metadata
        │
        ▼
training_metadata
        │
        ▼
training_data_processing
```

with:

```text
training_analysis_worker
```

running when automated behavioral processing is required.

No imaging module is required.

---

### Full Local Workflow

The complete workflow can use:

```text
animals_metadata
virus_metadata
imaging_metadata
imaging_analysis_metadata
training_metadata
training_data_processing
```

together with:

```text
imaging_analysis_worker
training_analysis_worker
```

---

## PostgreSQL Database

StimBEAM uses **PostgreSQL** as its relational metadata database.

The Django configuration reads database connection information from environment variables rather than embedding database credentials directly in the source code.

The current development architecture is:

```text
Django
   │
   │ PostgreSQL connection
   ▼
Docker Engine
   │
   ▼
PostgreSQL 16 container
   │
   ▼
Persistent PostgreSQL volume
```

The PostgreSQL Docker volume allows database contents to persist independently of the lifecycle of the PostgreSQL container.

---

## Docker

The repository currently contains a Docker Compose configuration for the PostgreSQL development database.

At the current development stage:

```text
Host workstation
│
├── Django application
├── Imaging analysis worker
├── Training analysis worker
│
└── Docker Engine
       │
       └── PostgreSQL
```

The intended future architecture is more completely containerized.

Conceptually:

```text
                Container orchestration
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
 Django web          PostgreSQL       Optional workers
  service             service               │
                                           ├── imaging-analysis worker
                                           └── training-analysis worker
```

Different deployments can enable only the services required by a research group.

---

## Scaling Beyond a Local Workstation

The current implementation is primarily a development deployment running on a local workstation.

The architecture is intended to support future scaling toward:

```text
Local development
        │
        ▼
Research-group deployment
        │
        ▼
Laboratory deployment
        │
        ▼
Institutional deployment
```

Containerization can provide reproducible service environments while deployment-specific configuration determines database credentials, storage locations, enabled modules, and optional workers.

Experimental datasets themselves should remain on appropriate persistent scientific storage rather than inside disposable application containers.

---

## Audit History and Track Changes

The project uses `django-simple-history` together with application-level Track Changes records.

The goal is to retain a human-readable audit trail showing when experimental metadata was:

```text
Created
Updated
Deleted
```

and, where available:

- when the change occurred;
- who made the change;
- which fields changed;
- old and new values.

Audit tracking is currently implemented across multiple metadata domains.

This is particularly useful for collaborative laboratory metadata management where records may be edited by multiple researchers.

---

## Technology Stack

### Web and Metadata

- Python
- Django
- Django Admin
- PostgreSQL
- django-simple-history

### Infrastructure

- Docker
- Docker Compose
- Environment-based configuration
- Persistent PostgreSQL storage

### Imaging Analysis

- Suite2P-based processing
- Python scientific-computing ecosystem
- Independent background worker

### Behavioral Processing

- BPod behavioral data
- Python-based training-data processing
- Licking-data extraction
- Independent background worker

### Development

- Git
- GitHub

---

## Repository Philosophy

The project follows several architectural principles.

### 1. One Codebase, Multiple Experimental Workflows

Different laboratories should not require permanent Git branches simply because their experimental workflows differ.

Instead:

```text
                       One repository
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
    Imaging group     Behavior group     Full workflow
```

Deployment configuration should eventually determine which modules and services are enabled.

---

### 2. Scientific Domains Remain Modular

Experimental functionality is separated according to domain:

```text
Animals
Viruses
Imaging
Imaging Analysis
Training
Training Data Processing
```

Optional modules should not unnecessarily depend on unrelated experimental domains.

---

### 3. Metadata and Large Scientific Data Are Different

PostgreSQL stores structured metadata and references to scientific files.

Large experimental files such as MESC imaging data and BPod source files remain on dedicated filesystem or institutional scientific storage.

---

### 4. Long-Running Processing Does Not Belong in Web Requests

Scientific processing can take significantly longer than a normal web request.

Therefore:

```text
Django
   │
   └── creates / manages jobs

Background worker
   │
   └── performs scientific processing
```

This keeps the web application responsive while allowing analysis jobs to run independently.

---

### 5. Git Branches Are for Development, Not Laboratory Configurations

Feature development can occur on temporary branches such as:

```text
feature/imaging-module
feature/training-module
feature/"NEW-MODULE"
```

and then be merged into:

```text
main
```

Different research groups should eventually select modules through deployment configuration rather than maintaining long-lived laboratory-specific branches.

---

## Current Development Status

⚠️ **StimBEAM is under active development.**

The current repository represents an evolving research-software framework rather than a finished institutional product.

Current development includes:

- modular experimental metadata apps;
- PostgreSQL-backed metadata storage;
- Dockerized PostgreSQL development infrastructure;
- audit/change tracking;
- imaging-session management;
- protocol-specific imaging-analysis job processing;
- behavioral-training metadata;
- mouse body-weight tracking;
- automated training-data processing;
- independent imaging and training background workers.

Future development can extend:

- complete containerization of application services;
- configurable module/deployment profiles;
- permissions and research-group access control;
- automated deployment;
- automated testing of different module combinations;
- institutional storage integration;
- improved scientific provenance;
- production deployment and backup strategies.

---

## Project Status

This project is currently being developed for research use.

The long-term objective is a reproducible and modular framework that can support different experimental workflows without forcing every research group to install or use unrelated components.

```text
Shared metadata foundation
           │
           ├── Imaging
           │      └── optional imaging analysis
           │
           ├── Training
           │      └── optional behavioral processing
           │
           └── additional experimental domains
```

The framework is therefore intended to grow by adding or enabling experimental modules rather than by creating separate versions of the entire project for each laboratory.

Credits: [Abhrajyoti Chakrabarti](https://ajax5692.github.io/personal-webpage-cv/)
