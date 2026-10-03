import { useEffect, useRef } from 'react';
import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl';
import mapLibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { makeVehicleCollection } from './domain.js';

// Vite prebundles dependencies as module URLs that MapLibre cannot use to
// infer the adjacent worker file. Importing it as an asset gives the worker a
// browser-served URL in both development and static builds.
setWorkerUrl(mapLibreWorkerUrl);

const EMPTY = { type: 'FeatureCollection', features: [] };

function initialStyle() {
  return {
    version: 8,
    sources: {
      osm: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
        maxzoom: 19,
      },
      network: {
        type: 'geojson',
        data: EMPTY,
        attribution: 'Translink / Queensland Department of Transport and Main Roads · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>',
      },
      vehicles: { type: 'geojson', data: EMPTY },
    },
    layers: [
      { id: 'osm-background', type: 'raster', source: 'osm', paint: { 'raster-opacity': 0.9 } },
      {
        id: 'bus-routes', type: 'line', source: 'network',
        filter: ['all', ['==', ['get', 'kind'], 'shape'], ['==', ['get', 'mode'], 'bus']],
        paint: { 'line-color': '#158a80', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.1, 14, 2.4], 'line-opacity': 0.82 },
      },
      {
        id: 'rail-routes', type: 'line', source: 'network',
        filter: ['all', ['==', ['get', 'kind'], 'shape'], ['==', ['get', 'mode'], 'rail']],
        paint: { 'line-color': '#d67563', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.7, 14, 3.3], 'line-opacity': 0.92 },
      },
      {
        id: 'other-routes', type: 'line', source: 'network',
        filter: ['all', ['==', ['get', 'kind'], 'shape'], ['!', ['in', ['get', 'mode'], ['literal', ['bus', 'rail']]]]],
        paint: { 'line-color': '#84959b', 'line-width': 1.3, 'line-opacity': 0.4 },
      },
      {
        id: 'stops', type: 'circle', source: 'network',
        filter: ['==', ['get', 'kind'], 'stop'],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 2.1, 14, 4], 'circle-color': '#fffdf8', 'circle-stroke-color': '#24474a', 'circle-stroke-width': 1.2 },
      },
      {
        id: 'stations', type: 'circle', source: 'network',
        filter: ['==', ['get', 'kind'], 'station'],
        paint: { 'circle-radius': 6, 'circle-color': '#f1b45e', 'circle-stroke-color': '#fffdf8', 'circle-stroke-width': 2 },
      },
      {
        id: 'recorded-vehicles', type: 'circle', source: 'vehicles',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 6.5],
          'circle-color': ['match', ['get', 'quality'], 'fresh', '#047f73', 'stale', '#e2a247', 'unmatched', '#7d9098', 'unknown', '#bf766c', '#7d9098'],
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5, 'circle-opacity': 0.96,
        },
      },
    ],
  };
}

export default function ReplayMap({ network, display, visibleLayers, onStopSelect, onVehicleSelect }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: initialStyle(),
      center: [153.025, -27.485],
      zoom: 12.6,
      minZoom: 10,
      maxZoom: 18,
      attributionControl: true,
      maxTileCacheSize: 128,
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    const resizeObserver = typeof ResizeObserver === 'function'
      ? new ResizeObserver(() => map.resize())
      : null;
    resizeObserver?.observe(containerRef.current);

    map.on('load', () => {
      map.resize();
      readyRef.current = true;
      map.getSource('network')?.setData(network ?? EMPTY);
      map.getSource('vehicles')?.setData(makeVehicleCollection(display));
    });
    map.on('click', 'stops', (event) => {
      const feature = event.features?.[0];
      if (feature) onStopSelect?.(feature.properties ?? {});
    });
    map.on('click', 'stations', (event) => {
      const feature = event.features?.[0];
      if (feature) onStopSelect?.(feature.properties ?? {});
    });
    map.on('click', 'recorded-vehicles', (event) => {
      const feature = event.features?.[0];
      if (feature) onVehicleSelect?.(feature.properties ?? {});
    });
    for (const layer of ['stops', 'stations', 'recorded-vehicles']) {
      map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
    }

    return () => {
      resizeObserver?.disconnect();
      readyRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.getSource('network')?.setData(network ?? EMPTY);
    map.getSource('vehicles')?.setData(makeVehicleCollection(display));
  }, [network, display]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const visibility = {
      'bus-routes': visibleLayers?.bus ? 'visible' : 'none',
      'rail-routes': visibleLayers?.rail ? 'visible' : 'none',
      stops: visibleLayers?.stops ? 'visible' : 'none',
      stations: visibleLayers?.stops ? 'visible' : 'none',
      'recorded-vehicles': visibleLayers?.vehicles ? 'visible' : 'none',
    };
    for (const [layer, value] of Object.entries(visibility)) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', value);
    }
  }, [visibleLayers]);

  return <div className="map-canvas" ref={containerRef} aria-label="Map of recorded Brisbane transit service" />;
}
