import React, { useEffect, useState } from 'react';
import {
  createExperiment,
  fetchCapabilities,
  fetchExperiment,
  fetchWorkloads,
  reselectConfiguration,
  restoreSettings,
} from './api';
import { CalibrationView } from './components/CalibrationView';
import { ExplorerView } from './components/ExplorerView';
import { Navbar } from './components/Navbar';
import { SetupView } from './components/SetupView';
import { ValidationView } from './components/ValidationView';
import { WatchPanel } from './components/WatchPanel';
import { CapabilitiesResponse, Experiment, WorkloadInfo } from './types';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'setup' | 'explorer' | 'calibration' | 'validation' | 'watch'>('explorer');
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [workloads, setWorkloads] = useState<WorkloadInfo[]>([]);
  const [experiment, setExperiment] = useState<Experiment | null>(null);

  // Setup view state
  const [selectedWorkload, setSelectedWorkload] = useState<string>('clean_build');
  const [objective, setObjective] = useState<string>('deadline');
  const [runtimeBudgetS, setRuntimeBudgetS] = useState<number | null>(45.0);
  const [energyTargetPct, setEnergyTargetPct] = useState<number>(70);
  const [perfFloorPct, setPerfFloorPct] = useState<number>(90);
  const [calibrationBudgetS, setCalibrationBudgetS] = useState<number | null>(120);

  // Status flags
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isRestoring, setIsRestoring] = useState<boolean>(false);
  const [restorationStatus, setRestorationStatus] = useState<string>('restored');
  const [experimentState, setExperimentState] = useState<string | null>(null);
  const [runProgress, setRunProgress] = useState<{ index: number; total: number; configId?: string } | null>(null);
  const [experimentStateMessage, setExperimentStateMessage] = useState<string | null>(null);

  useEffect(() => {
    // Initial data fetch
    fetchCapabilities()
      .then((caps) => {
        setCapabilities(caps);
        setRestorationStatus(caps.restoration.status);
      })
      .catch((e) => console.warn('Could not fetch capabilities:', e));

    fetchWorkloads()
      .then(setWorkloads)
      .catch((e) => console.warn('Could not fetch workloads:', e));

    fetchExperiment('exp_demo_clean_build')
      .then((e) => {
        setExperiment(e);
        if (e.state) setExperimentState(e.state);
      })
      .catch((e) => console.warn('Could not fetch default experiment:', e));
  }, []);

  // Listen for SSE events when an experiment is active
  useEffect(() => {
    if (!experiment) return;

    const eventSource = new EventSource(`/api/experiments/${experiment.id}/events`);

    eventSource.addEventListener('run_progress', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        setRunProgress({ index: d.run_index ?? 0, total: d.total_runs ?? 0, configId: d.config_id });
      } catch { /* ignore malformed */ }
    });

    eventSource.addEventListener('run_complete', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        setRunProgress({ index: d.run_index ?? 0, total: d.total_runs ?? 0, configId: d.config_id });
        // refresh the experiment so the explorer picks up live run rows as they land
        fetchExperiment(experiment.id)
          .then((full) => setExperiment(full))
          .catch(() => { /* transient */ });
      } catch { /* ignore malformed */ }
    });

    eventSource.addEventListener('experiment_state', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.state && data.state !== 'profiling') setRunProgress(null);
        if (data.state) setExperimentState(data.state);
        setExperimentStateMessage(data.message ?? data.reason ?? null);
        if (data.state === 'selected' || data.state === 'failed') {
          fetchExperiment(experiment.id).then((full) => setExperiment(full)).catch(() => {});
        }
      } catch { /* ignore malformed */ }
    });

    eventSource.addEventListener('restore_status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setRestorationStatus(data.status);
      } catch (err) {
        console.error(err);
      }
    });

    return () => {
      eventSource.close();
    };
  }, [experiment?.id]);

  const handleStartExperiment = async () => {
    try {
      setIsStarting(true);
      const res = await createExperiment({
        workload_id: selectedWorkload,
        objective,
        runtime_budget_s: runtimeBudgetS,
        preference:
          objective === 'preference'
            ? { energy_target_pct: energyTargetPct, perf_floor_pct: perfFloorPct }
            : undefined,
        calibration_budget_s: calibrationBudgetS ?? undefined,
      });
      const fullExp = await fetchExperiment(res.id);
      setExperiment(fullExp);
      setActiveTab('explorer');
    } catch (e: any) {
      alert(`Error starting experiment: ${e.message}`);
    } finally {
      setIsStarting(false);
    }
  };

  const handleEmergencyRestore = async () => {
    try {
      setIsRestoring(true);
      const res = await restoreSettings();
      setRestorationStatus(res.status);
      alert('Hardware settings restored and verified.');
    } catch (e: any) {
      alert(`Restore failed: ${e.message}`);
    } finally {
      setIsRestoring(false);
    }
  };

  const handleReselect = async (budgetS: number) => {
    if (!experiment) return;
    try {
      const updatedSel = await reselectConfiguration(experiment.id, {
        objective: experiment.objective,
        runtime_budget_s: budgetS,
        preference: experiment.preference,
        headroom_pct: 5.0,
      });
      setExperiment((prev) => (prev ? { ...prev, selection: updatedSel } : null));
    } catch (e) {
      console.error('Failed to reselect:', e);
    }
  };

  const handleApplySuggestedBudget = (budgetS: number) => {
    setRuntimeBudgetS(budgetS);
    setActiveTab('setup');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        restorationStatus={restorationStatus}
        onEmergencyRestore={handleEmergencyRestore}
        isRestoring={isRestoring}
        experimentState={experimentState}
        experimentStateMessage={experimentStateMessage}
        runProgress={runProgress}
      />

      <main style={{ flex: 1, padding: '1.5rem', maxWidth: '1300px', width: '100%', margin: '0 auto', boxSizing: 'border-box' }}>
        {activeTab === 'setup' && (
          <SetupView
            capabilities={capabilities}
            workloads={workloads}
            selectedWorkload={selectedWorkload}
            onSelectWorkload={setSelectedWorkload}
            objective={objective}
            onChangeObjective={setObjective}
            runtimeBudgetS={runtimeBudgetS}
            onChangeRuntimeBudget={setRuntimeBudgetS}
            energyTargetPct={energyTargetPct}
            onChangeEnergyTarget={setEnergyTargetPct}
            perfFloorPct={perfFloorPct}
            onChangePerfFloor={setPerfFloorPct}
            calibrationBudgetS={calibrationBudgetS}
            onChangeCalibrationBudget={setCalibrationBudgetS}
            onStartExperiment={handleStartExperiment}
            isStarting={isStarting}
            baselineRuntimeS={
              experiment?.profile?.baseline_config_id
                ? experiment.profile.configurations?.[experiment.profile.baseline_config_id]?.median_runtime_s ?? null
                : null
            }
          />
        )}

        {activeTab === 'explorer' && experiment && (
          <ExplorerView
            experiment={experiment}
            onReselect={handleReselect}
            onNavigateValidation={() => setActiveTab('validation')}
          />
        )}

        {activeTab === 'calibration' && <CalibrationView />}

        {activeTab === 'validation' && experiment && (
          <ValidationView experiment={experiment} />
        )}

        {activeTab === 'watch' && (
          <WatchPanel onApplySuggestedBudget={handleApplySuggestedBudget} />
        )}
      </main>
    </div>
  );
};
