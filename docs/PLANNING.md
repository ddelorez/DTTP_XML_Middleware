# Planning Document: Daikin XML Listener Middleware for S3 and Snowflake

## Objective
Develop a lightweight middleware to aggregate XML event streams from an Avigilon ACM (Unity Access) system into an S3 bucket, ensuring compatibility with Snowflake for data ingestion, processing, and reporting. The middleware will be delivered as a Docker container image with source code, allowing customer maintenance and modification. The project root directory is `Daikin XML Listener`, and a reference PDF file (`XML Events Collaboration.pdf`) illustrating the XML collaboration setup and sample data is located in the `./Reference Docs/` subdirectory. Code generation will leverage the Context7 MCP server and the SoftwarePlanning MCP from `github.com/NightTrek/Software-planning-mcp` to enhance the process.

## Requirements
- **Input:** Listen for TCP-based XML event streams (e.g., `<EVENT>` blocks with `<plasectrxEventname>`, `<plasectrxRecdate>`, etc.) on a configurable host/port, as defined in the Avigilon ACM system (e.g., Host IP, Port Number, Require TCP). See `./Reference Docs/XML Events Collaboration.pdf` for setup details and sample `<EVENT>` data.
- **Output:** Aggregate raw XML data into timestamped files (e.g., `20250729_161500.xml`) in an S3 bucket, with a root `<EVENTS>` element to ensure well-formed XML for Snowflake.
- **Snowflake Compatibility:** Ensure files are parseable by Snowflake's `FILE_FORMAT = (TYPE = XML)` for ingestion into a `VARIANT` column, supporting queries on fields like `<plasectrxIsAlarm>` or `<plasectrxSourceName>` as shown in the PDF.
- **Dockerization:** Package the middleware as a Docker container using `python:alpine`, exposing the TCP port and configurable via environment variables.
- **Maintainability:** Provide clean, commented Python source code (~250-300 lines) for customer modification (e.g., changing rotation intervals, adding JSON output).
- **Error Handling:** Handle connection drops, malformed XML, and S3 upload failures gracefully.
- **Optional Enhancement:** Support JSON output as an alternative for better Snowflake performance, configurable via an environment variable.

## Architecture
- **Components:**
  - **TCP Server:** Listens on a configurable port (default: 8080) for XML event streams, appending raw data to a local file (`current.xml`).
  - **File Rotation:** Rotates the file hourly or at 10MB, wrapping contents in `<EVENTS>` for well-formed XML, then uploads to S3.
  - **S3 Client:** Uses `boto3` to upload files to a specified bucket and prefix (e.g., `s3://<bucket>/xml-events/`).
  - **Threading:** Uses a background thread for file rotation/upload to avoid blocking the TCP server.
- **Flow:**
  1. Avigilon ACM sends XML events (e.g., `<EVENT><plasectrxEventname>Input point in alarm</plasectrxEventname>...</EVENT>`, see `./Reference Docs/XML Events Collaboration.pdf`) to the middleware’s IP/port.
  2. Middleware appends raw data to `current.xml`.
  3. On rotation (hourly or 10MB), wraps content in `<EVENTS>`, validates XML, and uploads as `s3://<bucket>/xml-events/<timestamp>.xml`.
  4. Snowflake ingests files via a Stage and `COPY INTO`, storing data in a `VARIANT` column for querying.
- **Optional JSON Mode:** Convert XML to JSON arrays (e.g., `[{ "plasectrxEventname": "Input point in alarm", ... }]`), uploading as `.json` files if enabled.

## Implementation Details
- **Language:** Python 3.12 (standard library + `boto3` for S3).
- **Libraries:**
  - `socket`: For TCP server.
  - `threading`: For concurrent file rotation.
  - `boto3`: For S3 uploads.
  - `xml.etree.ElementTree`: For XML wrapping/validation.
  - `os`, `time`, `datetime`: For file management and timestamps.
  - `json` (optional): For JSON output.
- **File Structure (in `./Daikin XML Listener/`):**
  - `server.py`: Main middleware script (~250 lines).
  - `Dockerfile`: Builds the container image.
  - `README.md`: Instructions for building, running, and configuring.
  - `./Reference Docs/XML Events Collaboration.pdf`: Reference document with XML collaboration setup and sample data (e.g., `<EVENT>` block for "input point in alarm").
- **Environment Variables:**
  - `PORT`: TCP port to listen on (default: 8080).
  - `BUCKET_NAME`: S3 bucket for uploads (required).
  - `PREFIX`: S3 key prefix (default: `xml-events/`).
  - `ROTATION_INTERVAL`: File rotation interval in seconds (default: 3600).
  - `MAX_FILE_SIZE`: Max file size in bytes (default: 10MB).
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`: AWS credentials and region.
  - `OUTPUT_FORMAT` (optional): `xml` or `json` (default: `xml`).
- **Error Handling:**
  - Re-listen on connection drops.
  - Fallback to raw content upload if XML validation fails.
  - Log errors to console (extendable to S3 logs).
- **Docker:**
  - Base image: `python:alpine` (improved security, zero vulnerabilities).
  - Install `boto3` via `pip`.
  - Expose `PORT` (e.g., 8080).
  - Run `python server.py` as entrypoint.
- **Snowflake Integration:**
  - Output files must be well-formed XML (or JSON) for `COPY INTO`.
  - File names include UTC timestamps (e.g., `20250729_161500.xml`) for traceability.
  - Optional date-based S3 folders (e.g., `xml-events/2025/07/29/`) for partitioning.

## Code Generation with Kilo Code
- **MCP Servers:**
  - **Context7 MCP Server:** Leverage for contextual code synthesis, ensuring the generated `server.py` aligns with the XML event structure (e.g., `<EVENT>` blocks from `./Reference Docs/XML Events Collaboration.pdf`) and handles real-time streaming requirements.
  - **SoftwarePlanning MCP (`github.com/NightTrek/Software-planning-mcp`):** Use to structure the code generation process, ensuring modular design, adherence to PEP 8, and integration of error handling and configuration patterns.
- **Kilo Code Instructions:**
  - Parse this `Planning.md` in the `./Daikin XML Listener/` directory to guide code synthesis.
  - Use Context7 MCP to analyze the XML structure in `./Reference Docs/XML Events Collaboration.pdf` for accurate handling of `<EVENT>` blocks.
  - Use SoftwarePlanning MCP to enforce modular functions (e.g., separate TCP handling, file rotation, and S3 upload) and consistent error handling.
  - Ensure generated code adheres to existing VSCode Kilo Code style rules (e.g., PEP 8, descriptive variable names, docstrings).
  - Reference the PDF for sample data (e.g., "input point in alarm" event on page 524) during code generation and testing.

## Development Tasks
1. **TCP Server (server.py):**
   - Implement a socket server to listen on `PORT` and append raw data to `./current.xml`.
   - Use `threading` to handle multiple client connections concurrently.
   - Leverage Context7 MCP to ensure compatibility with XML stream format from the PDF.
2. **File Rotation and Upload:**
   - Create a background thread checking every 60 seconds for rotation triggers (time or size).
   - On rotation, wrap `./current.xml` in `<EVENTS>` using `xml.etree.ElementTree`, validate, and save to `./temp.xml`.
   - Upload to S3 with `boto3` as `<PREFIX><timestamp>.xml`.
   - Delete local files after upload.
   - Use SoftwarePlanning MCP to ensure modular rotation logic and robust error handling.
3. **Optional JSON Conversion:**
   - If `OUTPUT_FORMAT=json`, parse XML into a list of dictionaries and write as JSON.
   - Adjust S3 key extension to `.json`.
   - Use Context7 MCP to validate JSON output against XML structure in the PDF.
4. **Dockerfile:**
   - Use `python:alpine`, install `boto3`, copy `server.py`, expose `PORT`, and set `CMD`.
   - Ensure SoftwarePlanning MCP enforces clean Dockerfile structure.
5. **Documentation (README.md):**
   - Instructions for building (`docker build -t xml-stream-aggregator .` in `./Daikin XML Listener/`).
   - Running (`docker run -d -p <host_port>:<container_port> -e BUCKET_NAME=...`).
   - Environment variable descriptions.
   - Reference to `./Reference Docs/XML Events Collaboration.pdf` for XML structure.
   - Snowflake setup (Stage, `COPY INTO`, sample queries).
6. **Testing:**
   - Simulate XML stream with `nc` using sample `<EVENT>` data from `./Reference Docs/XML Events Collaboration.pdf`.
   - Verify S3 uploads and XML validity.
   - Test Snowflake ingestion with a sample file.
   - Use Context7 MCP to validate stream handling against PDF sample data.

## Coding Style (To Be Enforced by Kilo Code)
- Follow VSCode Kilo Code extension’s style rules (e.g., PEP 8 for Python).
- Use descriptive variable names (e.g., `CURRENT_FILE`, `ROTATION_INTERVAL`).
- Include docstrings for functions and inline comments for clarity.
- Handle exceptions explicitly (e.g., `socket.error`, `boto3.exceptions`).
- Keep functions short and single-purpose (e.g., separate TCP handling, rotation, and S3 upload).
- Use macOS-compatible file paths (e.g., `./current.xml`, `./Reference Docs/XML Events Collaboration.pdf`).
- Leverage SoftwarePlanning MCP to enforce modular code structure and style consistency.

## Deliverables
- **Source Code (in `./Daikin XML Listener/`):**
  - `server.py`: Middleware implementation.
  - `Dockerfile`: Container build script.
  - `README.md`: Setup and usage instructions.
  - `./Reference Docs/XML Events Collaboration.pdf`: Reference document (already provided).
- **Docker Image:** Built and tested image (`xml-stream-aggregator`).
- **Customer Hand-Off:**
  - Git repository with all files.
  - Instructions for building, running, and modifying.
  - Reference to PDF for XML structure and sample data.

## Snowflake Integration Notes
- **S3 Stage Setup:**
  ```sql
  CREATE STAGE my_s3_stage
  URL = 's3://<BUCKET_NAME>/<PREFIX>'
  CREDENTIALS = (AWS_KEY_ID = '<key>' AWS_SECRET_KEY = '<secret>')
  FILE_FORMAT = (TYPE = XML);
  ```
- **Table Schema:**
  ```sql
  CREATE TABLE xml_events (
    event_data VARIANT,
    load_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
  );
  ```
- **Ingestion:**
  ```sql
  COPY INTO xml_events (event_data)
  FROM @my_s3_stage
  FILE_FORMAT = (TYPE = XML)
  ON_ERROR = 'CONTINUE';
  ```
- **Sample Query:**
  ```sql
  SELECT
    GET_PATH(PARSE_XML(event_data), 'EVENT/plasectrxEventname')::STRING AS event_name,
    GET_PATH(PARSE_XML(event_data), 'EVENT/plasectrxRecdate')::TIMESTAMP AS rec_date
  FROM xml_events
  WHERE event_name = 'Input point in alarm';
  ```

## Next Steps
- Place this `Planning.md` in `./Daikin XML Listener/` for Kilo Code to process.
- Configure Kilo Code to use Context7 MCP server and SoftwarePlanning MCP (`github.com/NightTrek/Software-planning-mcp`) for code synthesis.
- Reference `./Reference Docs/XML Events Collaboration.pdf` for XML structure and sample data during development and testing.
- Test with a simulated XML stream (e.g., via `nc` with sample `<EVENT>` data from the PDF).
- Validate S3 uploads and Snowflake ingestion.
- Package and document for customer hand-off.