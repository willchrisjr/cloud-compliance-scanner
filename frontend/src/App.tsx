import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { format } from 'date-fns'; // Import date-fns
import './App.css';

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

// Define possible sortable columns
type SortableColumn = 'scan_timestamp' | 'gcp_project_id' | 'resource_type' | 'resource_id' | 'status';
type SortDirection = 'asc' | 'desc';

interface SortConfig {
  key: SortableColumn;
  direction: SortDirection;
}

// Define available checks (match keys in backend main.py)
const AVAILABLE_CHECKS = {
    public_buckets: "Public Buckets",
    firewall_rules: "Risky Firewall Rules",
    iam_bindings: "Primitive IAM Roles",
    default_sa_usage: "Default SA Usage",
    unused_resources: "Unused Disks/IPs",
    bucket_logging: "Bucket Logging Disabled",
};
type CheckName = keyof typeof AVAILABLE_CHECKS;


// --- Components ---

// Input and Scan Button Component
const ProjectInput: React.FC<{
  projectId: string;
  setProjectId: (id: string) => void;
  onScan: () => void;
  isScanning: boolean;
}> = ({ projectId, setProjectId, onScan, isScanning }) => (
  <div className="project-input-container">
    <input
      type="text"
      value={projectId}
      onChange={(e) => setProjectId(e.target.value)}
      placeholder="Enter GCP Project ID"
      disabled={isScanning}
      aria-label="GCP Project ID"
    />
    <button onClick={onScan} disabled={isScanning || !projectId.trim()}>
      {isScanning ? 'Scanning...' : 'Run Compliance Scan'}
    </button>
  </div>
);

// Check Selection Component
const CheckSelector: React.FC<{
    selectedChecks: CheckName[];
    setSelectedChecks: (checks: CheckName[]) => void;
    disabled: boolean;
}> = ({ selectedChecks, setSelectedChecks, disabled }) => {

    const handleCheckChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const { name, checked } = event.target;
        const checkName = name as CheckName;

        if (checked) {
            setSelectedChecks([...selectedChecks, checkName]);
        } else {
            setSelectedChecks(selectedChecks.filter((c) => c !== checkName));
        }
    };

    const handleSelectAll = (event: React.ChangeEvent<HTMLInputElement>) => {
        if (event.target.checked) {
            setSelectedChecks(Object.keys(AVAILABLE_CHECKS) as CheckName[]);
        } else {
            setSelectedChecks([]);
        }
    };

    const allSelected = selectedChecks.length === Object.keys(AVAILABLE_CHECKS).length;

    return (
        <div className="check-selector-container">
            <h4>Select Checks to Run:</h4>
            <div className="check-option">
                 <input
                    type="checkbox"
                    id="check-all"
                    name="all"
                    checked={allSelected}
                    onChange={handleSelectAll}
                    disabled={disabled}
                />
                <label htmlFor="check-all">All Checks</label>
            </div>
            {Object.entries(AVAILABLE_CHECKS).map(([key, label]) => (
                <div key={key} className="check-option">
                    <input
                        type="checkbox"
                        id={`check-${key}`}
                        name={key}
                        checked={selectedChecks.includes(key as CheckName)}
                        onChange={handleCheckChange}
                        disabled={disabled}
                    />
                    <label htmlFor={`check-${key}`}>{label}</label>
                </div>
            ))}
        </div>
    );
};


// Filter Input Component
const FilterInput: React.FC<{
    filterText: string;
    setFilterText: (text: string) => void;
    disabled: boolean;
}> = ({ filterText, setFilterText, disabled }) => (
    <div className="filter-container">
        <input
            type="text"
            placeholder="Filter findings..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            disabled={disabled}
            aria-label="Filter findings"
        />
    </div>
);


// Findings Table Component
const FindingsTable: React.FC<{
  findings: Finding[];
  requestSort: (key: SortableColumn) => void;
  sortConfig: SortConfig | null;
}> = ({ findings, requestSort, sortConfig }) => {
  const getSortDirectionIndicator = (key: SortableColumn) => {
    if (!sortConfig || sortConfig.key !== key) {
      return null; // No indicator
    }
    return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            <th onClick={() => requestSort('scan_timestamp')}>
              Timestamp{getSortDirectionIndicator('scan_timestamp')}
            </th>
            <th onClick={() => requestSort('gcp_project_id')}>
              Project ID{getSortDirectionIndicator('gcp_project_id')}
            </th>
            <th onClick={() => requestSort('resource_type')}>
              Resource Type{getSortDirectionIndicator('resource_type')}
            </th>
            <th onClick={() => requestSort('resource_id')}>
              Resource ID{getSortDirectionIndicator('resource_id')}
            </th>
            <th>Description</th> {/* Not sorting description for simplicity */}
            <th onClick={() => requestSort('status')}>
              Status{getSortDirectionIndicator('status')}
            </th>
          </tr>
        </thead>
        <tbody>
          {findings.length === 0 ? (
            <tr>
              <td colSpan={6}>No findings match the current filter.</td>
            </tr>
          ) : (
            findings.map((finding) => (
              <tr key={finding.id}>
                <td>{format(new Date(finding.scan_timestamp), 'Pp')}</td> {/* Use date-fns */}
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
    </div>
  );
};

// --- Main App Component ---

function App() {
  const [projectId, setProjectId] = useState<string>('');
  const [allFindings, setAllFindings] = useState<Finding[]>([]); // Store raw findings
  const [isLoading, setIsLoading] = useState<boolean>(false); // General loading state
  const [isScanning, setIsScanning] = useState<boolean>(false); // Specific state for scan button
  const [error, setError] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<string | null>(null);
  const [filterText, setFilterText] = useState<string>('');
  const [sortConfig, setSortConfig] = useState<SortConfig | null>(null);
  // State for selected checks - default to all initially
  const [selectedChecks, setSelectedChecks] = useState<CheckName[]>(Object.keys(AVAILABLE_CHECKS) as CheckName[]);


  // Backend API URL - adjust if your backend runs elsewhere
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080';

  // Function to fetch findings
  const fetchFindings = useCallback(async () => {
    // Use general loading indicator for fetches
    setIsLoading(true);
    setError(null);
    const url = `${API_URL}/findings`; // Fetch all initially

    try {
      const response = await fetch(url);
      if (!response.ok) {
        // Attempt to read error details from backend if available
        let errorDetail = response.statusText;
        try {
            const errorResult = await response.json();
            errorDetail = errorResult?.detail || errorDetail;
        } catch { // Ignore the error variable completely
            // Ignore if response is not JSON
        }
        throw new Error(`Failed to fetch findings: ${errorDetail}`);
      }
      const data: Finding[] = await response.json();
      setAllFindings(data);
      setScanStatus(null); // Clear scan status after successful fetch
    } catch (err) {
      if (err instanceof Error) {
        setError(`Error fetching findings: ${err.message}`);
      } else {
        setError('An unknown error occurred while fetching findings.');
      }
      setAllFindings([]); // Clear findings on error
    } finally {
      setIsLoading(false);
    }
  }, [API_URL]);

  // Fetch findings on initial load
  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  // Function to trigger a scan
  const handleScan = async () => {
    if (!projectId.trim() || selectedChecks.length === 0) return; // Basic validation + check if any checks selected
    setIsScanning(true); // Use specific scanning state
    setIsLoading(true); // Also set general loading
    setError(null);
    setScanStatus('Scan in progress...'); // Provide immediate feedback

    // Determine checks to send: if all are selected, send null/empty or specific 'all' keyword if backend expects it
    // Our backend handles empty list as "run all", so sending the actual list works.
    const checksPayload = selectedChecks.length === Object.keys(AVAILABLE_CHECKS).length ? null : selectedChecks;


    try {
      const response = await fetch(`${API_URL}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id: projectId.trim(),
            checks_to_run: checksPayload // Send selected checks (or null for all)
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        const errorDetail = result?.detail || response.statusText;
        throw new Error(`Scan failed: ${errorDetail}`);
      }

      setScanStatus(result.message || 'Scan completed successfully!');
      // After scan, refresh all findings to include the new ones
      fetchFindings();

    } catch (err) {
      if (err instanceof Error) {
        setError(`Error triggering scan: ${err.message}`);
        setScanStatus('Scan failed.');
      } else {
        setError('An unknown error occurred during the scan.');
        setScanStatus('Scan failed.');
      }
    } finally {
      // Loading/Scanning state is reset by fetchFindings completing
      setIsScanning(false);
    }
  };

  // Function to clear displayed findings (UI only)
  const handleClearFindings = () => {
      setAllFindings([]);
      setFilterText(''); // Also clear filter
      setSortConfig(null); // Reset sort
      setError(null);
      setScanStatus('Findings cleared from view.');
  };

  // Memoized sorting logic
  const sortedFindings = useMemo(() => {
    const sortableItems = [...allFindings]; // Use const
    if (sortConfig !== null) {
      sortableItems.sort((a, b) => {
        const aValue = a[sortConfig.key];
        const bValue = b[sortConfig.key];
        if (aValue < bValue) {
          return sortConfig.direction === 'asc' ? -1 : 1;
        }
        if (aValue > bValue) {
          return sortConfig.direction === 'asc' ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [allFindings, sortConfig]);

  // Memoized filtering logic
  const filteredFindings = useMemo(() => {
    if (!filterText) {
      return sortedFindings; // Return sorted if no filter
    }
    const lowerCaseFilter = filterText.toLowerCase();
    return sortedFindings.filter((finding) => {
      // Check multiple fields for the filter text
      return (
        finding.gcp_project_id.toLowerCase().includes(lowerCaseFilter) ||
        finding.resource_type.toLowerCase().includes(lowerCaseFilter) ||
        finding.resource_id.toLowerCase().includes(lowerCaseFilter) ||
        finding.finding_description.toLowerCase().includes(lowerCaseFilter) ||
        finding.status.toLowerCase().includes(lowerCaseFilter)
      );
    });
  }, [sortedFindings, filterText]);


  // Function to handle sort requests
  const requestSort = (key: SortableColumn) => {
    let direction: SortDirection = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  return (
    <div className="App">
      <h1>GCP Compliance Scanner</h1>

      <ProjectInput
        projectId={projectId}
        setProjectId={setProjectId}
        onScan={handleScan}
        isScanning={isScanning}
      />

       <CheckSelector
            selectedChecks={selectedChecks}
            setSelectedChecks={setSelectedChecks}
            disabled={isScanning || isLoading}
        />

      {/* Display Status/Error Messages */}
      {scanStatus && <p className={`status ${error ? 'error' : 'success'}`}>{scanStatus}</p>}
      {error && !scanStatus && <p className="error">{error}</p>}

      <h2>Compliance Findings</h2>

      <div className="controls-container">
        <FilterInput
            filterText={filterText}
            setFilterText={setFilterText}
            disabled={isLoading || isScanning}
        />
        <button onClick={handleClearFindings} disabled={isLoading || isScanning || allFindings.length === 0}>
            Clear View
        </button>
      </div>


      {/* Improved Loading Indicator */}
      {isLoading && <p className="loading-indicator">Loading data...</p>}

      {!isLoading && (
        <FindingsTable
          findings={filteredFindings} // Pass filtered (and sorted) findings
          requestSort={requestSort}
          sortConfig={sortConfig}
        />
      )}
    </div>
  );
}

export default App;
