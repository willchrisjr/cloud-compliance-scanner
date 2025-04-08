import React, { useState, useEffect, useCallback } from 'react';
import './App.css'; // We'll add some basic styles later

// Define the structure of a finding based on the backend response model
interface Finding {
  id: number;
  scan_timestamp: string;
  gcp_project_id: string;
  resource_type: string;
  resource_id: string;
  finding_description: string;
  status: string;
}

// Placeholder components - we will create these next
const ProjectInput: React.FC<{
  projectId: string;
  setProjectId: (id: string) => void;
  onScan: () => void;
  isLoading: boolean;
}> = ({ projectId, setProjectId, onScan, isLoading }) => (
  <div>
    <input
      type="text"
      value={projectId}
      onChange={(e) => setProjectId(e.target.value)}
      placeholder="Enter GCP Project ID"
      disabled={isLoading}
    />
    <button onClick={onScan} disabled={isLoading || !projectId}>
      {isLoading ? 'Scanning...' : 'Run Compliance Scan'}
    </button>
  </div>
);

const FindingsTable: React.FC<{ findings: Finding[] }> = ({ findings }) => (
  <table>
    <thead>
      <tr>
        <th>Timestamp</th>
        <th>Project ID</th>
        <th>Resource Type</th>
        <th>Resource ID</th>
        <th>Description</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {findings.length === 0 ? (
        <tr>
          <td colSpan={6}>No findings found.</td>
        </tr>
      ) : (
        findings.map((finding) => (
          <tr key={finding.id}>
            <td>{new Date(finding.scan_timestamp).toLocaleString()}</td>
            <td>{finding.gcp_project_id}</td>
            <td>{finding.resource_type}</td>
            <td>{finding.resource_id}</td>
            <td>{finding.finding_description}</td>
            <td>{finding.status}</td>
          </tr>
        ))
      )}
    </tbody>
  </table>
);
// End of placeholder components

function App() {
  const [projectId, setProjectId] = useState<string>('');
  const [findings, setFindings] = useState<Finding[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<string | null>(null);

  // Backend API URL - adjust if your backend runs elsewhere
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'; // Default to common local dev port

  // Function to fetch findings
  const fetchFindings = useCallback(async (filterProjectId?: string) => {
    setIsLoading(true);
    setError(null);
    const url = filterProjectId
      ? `${API_URL}/findings?project_id=${encodeURIComponent(filterProjectId)}`
      : `${API_URL}/findings`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch findings: ${response.statusText}`);
      }
      const data: Finding[] = await response.json();
      setFindings(data);
    } catch (err) {
      if (err instanceof Error) {
        setError(`Error fetching findings: ${err.message}`);
      } else {
        setError('An unknown error occurred while fetching findings.');
      }
      setFindings([]); // Clear findings on error
    } finally {
      setIsLoading(false);
    }
  }, [API_URL]); // Dependency array includes API_URL

  // Fetch all findings on initial load
  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]); // fetchFindings is memoized by useCallback

  // Function to trigger a scan
  const handleScan = async () => {
    if (!projectId) return;
    setIsLoading(true);
    setError(null);
    setScanStatus(null);

    try {
      const response = await fetch(`${API_URL}/scan`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ project_id: projectId }),
      });

      const result = await response.json(); // Read body once

      if (!response.ok) {
         // Try to get detail from FastAPI error response
         const errorDetail = result?.detail || response.statusText;
         throw new Error(`Scan failed: ${errorDetail}`);
      }

      setScanStatus(result.message || 'Scan completed successfully!');
      // After scan, refresh findings for the scanned project
      fetchFindings(projectId);

    } catch (err) {
       if (err instanceof Error) {
         setError(`Error triggering scan: ${err.message}`);
       } else {
         setError('An unknown error occurred during the scan.');
       }
      setScanStatus('Scan failed.');
    } finally {
      // Keep loading true until fetchFindings completes in the success case
      // setIsLoading(false); // isLoading is handled by fetchFindings
    }
  };

  return (
    <div className="App">
      <h1>GCP Compliance Scanner</h1>

      <ProjectInput
        projectId={projectId}
        setProjectId={setProjectId}
        onScan={handleScan}
        isLoading={isLoading}
      />

      {/* Display Scan Status/Error Messages */}
      {scanStatus && <p className={`status ${error ? 'error' : 'success'}`}>{scanStatus}</p>}
      {error && !scanStatus && <p className="error">{error}</p>} {/* Show fetch error if no scan status */}


      <h2>Compliance Findings</h2>
      {isLoading && findings.length === 0 && <p>Loading findings...</p>}
      <FindingsTable findings={findings} />

    </div>
  );
}

export default App;
